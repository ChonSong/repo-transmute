"""JSX/TSX component extraction for frontend migration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PropDef:
    """A component prop definition."""
    name: str
    type: str  # TypeScript type or 'any' if unknown
    default: str | None = None
    required: bool = True
    description: str = ""


@dataclass
class StateDef:
    """A useState or similar state definition."""
    name: str
    init_value: str  # initializer expression
    type: str = ""


@dataclass
class EffectDef:
    """A useEffect or similar effect definition."""
    deps: list[str]  # dependency list
    has_cleanup: bool = False
    description: str = ""


@dataclass
class APICallDef:
    """A frontend API call (fetch, axios, etc.)."""
    method: str  # GET, POST, etc.
    url_pattern: str  # the URL string or template
    function_name: str  # enclosing function name
    uses_sse: bool = False
    uses_websocket: bool = False
    auth: bool = False  # uses auth headers/tokens


@dataclass
class ImportDef:
    """An import statement."""
    module: str
    names: list[str]
    is_default: bool = False
    is_type: bool = False


@dataclass
class ComponentDef:
    """A single React component definition."""
    name: str
    file: str
    line: int
    is_default_export: bool = False
    props: list[PropDef] = field(default_factory=list)
    state: list[StateDef] = field(default_factory=list)
    effects: list[EffectDef] = field(default_factory=list)
    api_calls: list[APICallDef] = field(default_factory=list)
    imports: list[ImportDef] = field(default_factory=list)
    children_components: list[str] = field(default_factory=list)  # other components used
    hooks_used: list[str] = field(default_factory=list)  # hooks besides useState/useEffect
    has_jsx: bool = False
    jsx_complexity: int = 0  # rough count of JSX elements
    css_approach: str = ""  # tailwind, css-modules, styled-components, etc.
    theme_vars_used: list[str] = field(default_factory=list)  # CSS variables referenced
    tailwind_classes: list[str] = field(default_factory=list)  # unique tailwind classes


@dataclass
class RouteDef:
    """A route definition (from React Router, TanStack Router, etc.)."""
    path: str
    component: str
    file: str
    is_nested: bool = False
    loader: str = ""  # data loader function
    action: str = ""  # mutation action function


def extract_components_from_file(file_path: Path) -> list[ComponentDef]:
    """Extract React components from a single JSX/TSX file.
    
    Uses regex-based extraction (tree-sitter would be more precise but
    requires native bindings). This covers the common patterns:
    - function ComponentName() { ... }
    - const ComponentName = () => { ... }
    - export default ComponentName
    """
    content = file_path.read_text()
    lines = content.splitlines()
    components = []
    
    # Find component declarations
    # Pattern 1: function ComponentName(
    # Pattern 2: const ComponentName = (
    # Pattern 3: const ComponentName: React.FC = (
    func_pattern = re.compile(
        r'(?:export\s+)?(?:default\s+)?(?:function|const)\s+(\w+)'
        r'(?:\s*:\s*React\.FC)?'
        r'(?:<[^>]*>)?'  # generic type params
        r'\s*(?:\([^)]*\))?\s*(?:=>)?\s*(?:\{|=>)',
    )
    
    # Pattern for arrow function components on single line with JSX return
    arrow_pattern = re.compile(
        r'(?:export\s+)?(?:default\s+)?const\s+(\w+)\s*=\s*(?:\(.*?\))?\s*=>\s*(?:\(.+?\)|<)',
        re.DOTALL,
    )
    
    for match in func_pattern.finditer(content):
        comp_name = match.group(1)
        line_no = content[:match.start()].count('\n') + 1
        
        # Skip non-component patterns
        if comp_name.startswith('use') and not comp_name[3:4].isupper():
            continue  # custom hook, not a component
        if comp_name[0].islower():
            continue  # not a component by React convention
        
        comp = ComponentDef(
            name=comp_name,
            file=str(file_path),
            line=line_no,
            is_default_export='export default' in content[max(0, match.start()-20):match.start()],
        )
        
        # Extract component body (rough — from { to matching })
        body_start = content.find('{', match.end())
        if body_start >= 0:
            body_end = _find_matching_brace(content, body_start)
            if body_end > 0:
                body = content[body_start:body_end+1]
                _extract_props(body, comp)
                _extract_state(body, comp)
                _extract_effects(body, comp)
                _extract_api_calls(body, comp, comp_name)
                _extract_jsx_info(body, comp)
                _extract_css_info(body, comp)
        
        # Extract imports from the file
        _extract_imports(content, comp)
        
        components.append(comp)
    
    # Also find route definitions if present
    return components


def _find_matching_brace(content: str, start: int) -> int:
    """Find the closing brace matching the opening brace at start."""
    depth = 0
    i = start
    in_string = False
    string_char = None
    while i < len(content):
        c = content[i]
        if in_string:
            if c == string_char and (i == 0 or content[i-1] != '\\'):
                in_string = False
        elif c in ('"', "'", '`'):
            in_string = True
            string_char = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _extract_props(body: str, comp: ComponentDef):
    """Extract props from component body."""
    # Pattern: props interface/type definition
    # interface FooProps { bar: string; baz?: number; }
    type_pattern = re.compile(
        r'(?:interface|type)\s+\w*Props\w*\s*\{([^}]+)\}',
        re.DOTALL,
    )
    m = type_pattern.search(body)
    if m:
        props_block = m.group(1)
        for line in props_block.splitlines():
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            # bar: string; or bar?: string;
            prop_match = re.match(r'(\w+)(\?)?:\s*([^;]+)', line)
            if prop_match:
                prop = PropDef(
                    name=prop_match.group(1),
                    type=prop_match.group(3).strip(),
                    required=prop_match.group(2) != '?',
                )
                comp.props.append(prop)
    
    # Destructured props in function params: ({ foo, bar }: Props)
    destruct_pattern = re.compile(r'\(\s*\{([^}]+)\}')
    m = destruct_pattern.search(body[:500])  # Check near the top
    if m and not comp.props:
        names = [n.strip().split(':')[0].split('=')[0].strip()
                 for n in m.group(1).split(',')]
        for name in names:
            if name and name.isidentifier():
                comp.props.append(PropDef(name=name, type='any'))


def _extract_state(body: str, comp: ComponentDef):
    """Extract useState declarations."""
    # useState<Type>(initial) or useState(initial)
    state_pattern = re.compile(
        r'const\s+\[(\w+)\s*,\s*set(\w+)\]'
        r'\s*=\s*useState(?:<([^>]+)>)?\(([^)]*)\)',
    )
    found_state = False
    for m in state_pattern.finditer(body):
        found_state = True
        comp.state.append(StateDef(
            name=m.group(1),
            init_value=m.group(4) or 'undefined',
            type=m.group(3) or '',
        ))
    if found_state:
        comp.hooks_used.append('useState')


def _extract_effects(body: str, comp: ComponentDef):
    """Extract useEffect/useLayoutEffect declarations."""
    effect_pattern = re.compile(r'use(Effect|LayoutEffect|Memo|Callback)\s*\(')
    for m in effect_pattern.finditer(body):
        hook_name = 'use' + m.group(1)
        if hook_name not in comp.hooks_used:
            comp.hooks_used.append(hook_name)
        
        if hook_name in ('useEffect', 'useLayoutEffect'):
            # Try to find dependency array
            start = m.end()
            depth = 1
            i = start
            while i < len(body) and depth > 0:
                if body[i] == '(':
                    depth += 1
                elif body[i] == ')':
                    depth -= 1
                i += 1
            
            # Look for dependency array [...deps]
            dep_match = re.search(r'\[([^\]]*)\]', body[start:start+500])
            deps = []
            if dep_match:
                deps = [d.strip() for d in dep_match.group(1).split(',')
                        if d.strip() and d.strip() != '']
            
            has_cleanup = 'return' in body[start:i] and ('()' in body[start:i] or '=>' in body[start:i])
            
            comp.effects.append(EffectDef(
                deps=deps,
                has_cleanup=has_cleanup,
            ))


def _extract_api_calls(body: str, comp: ComponentDef, comp_name: str):
    """Extract API calls (fetch, axios, EventSource, WebSocket)."""
    # fetch() calls
    fetch_pattern = re.compile(r'fetch\(\s*[`\'"]([^`\'"]+)[`\'"]')
    for m in fetch_pattern.finditer(body):
        comp.api_calls.append(APICallDef(
            method='GET',  # default, may be overridden
            url_pattern=m.group(1),
            function_name=comp_name,
        ))
    
    # fetch with method
    fetch_method_pattern = re.compile(r'fetch\([^)]*method\s*:\s*[`\'"](\w+)[`\'"]')
    for m in fetch_method_pattern.finditer(body):
        # Update the last fetch call with the correct method
        if comp.api_calls:
            comp.api_calls[-1].method = m.group(1)
    
    # EventSource (SSE)
    if 'EventSource' in body or 'new EventSource' in body:
        for m in fetch_pattern.finditer(body):
            if comp.api_calls:
                comp.api_calls[-1].uses_sse = True
    
    # WebSocket
    if 'new WebSocket' in body or 'WebSocket(' in body:
        for m in fetch_pattern.finditer(body):
            if comp.api_calls:
                comp.api_calls[-1].uses_websocket = True


def _extract_jsx_info(body: str, comp: ComponentDef):
    """Extract JSX information."""
    # Count JSX elements (tags that start with < and have uppercase or known elements)
    jsx_tags = re.findall(r'<([A-Z]\w+|[a-z]\w+)\b', body)
    comp.jsx_complexity = len(jsx_tags)
    comp.has_jsx = len(jsx_tags) > 0
    comp.children_components = list({t for t in jsx_tags if t[0].isupper() and t != comp.name})
    comp.hooks_used.extend([h for h in ['useRef', 'useContext', 'useReducer']
                            if f'{h}(' in body and h not in comp.hooks_used])


def _extract_css_info(body: str, comp: ComponentDef):
    """Detect CSS approach and extract relevant information."""
    # Tailwind: className="..."
    tailwind_matches = re.findall(r'className="([^"]*)"', body)
    tailwind_matches += re.findall(r"className='([^']*)'", body)
    
    all_tw_classes = []
    for match in tailwind_matches:
        all_tw_classes.extend(match.split())
    comp.tailwind_classes = list({c for c in all_tw_classes if c and not c.startswith('{')})
    
    if comp.tailwind_classes:
        comp.css_approach = 'tailwind'
    
    # CSS modules: styles.xxx or className={styles.xxx}
    if re.search(r'styles\.\w+', body) or 'import styles from' in body:
        comp.css_approach = 'css-modules'
    
    # Styled components
    if 'styled.' in body or 'styled-components' in body:
        comp.css_approach = 'styled-components'
    
    # CSS variables: var(--xxx)
    css_var_matches = re.findall(r'var\((--[^)]+)\)', body)
    comp.theme_vars_used = list({v for v in css_var_matches})
    
    # theme.xxx or theme['xxx'] pattern
    if re.search(r'theme\.\w+', body) or 'useTheme' in body:
        if not comp.css_approach:
            comp.css_approach = 'theme-object'


def _extract_imports(content: str, comp: ComponentDef):
    """Extract import statements from the file."""
    # import { x, y } from 'module'
    import_pattern = re.compile(
        r"import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]"
    )
    for m in import_pattern.finditer(content):
        names = [n.strip().split(' as ')[0].strip() for n in m.group(1).split(',')]
        comp.imports.append(ImportDef(
            module=m.group(2),
            names=names,
            is_type='import type' in content[m.start()-5:m.start()],
        ))
    
    # import Default from 'module'
    default_import_pattern = re.compile(
        r"import\s+(?:type\s+)?(\w+)\s+from\s+['\"]([^'\"]+)['\"]"
    )
    for m in default_import_pattern.finditer(content):
        comp.imports.append(ImportDef(
            module=m.group(2),
            names=[m.group(1)],
            is_default=True,
            is_type='import type' in content[m.start()-5:m.start()],
        ))


def extract_routes_from_file(file_path: Path) -> list[RouteDef]:
    """Extract route definitions from a file.
    
    Handles:
    - React Router: <Route path="/foo" element={<Component />} />
    - TanStack Router: { path: '/foo', component: Component }
    - File-based routing comments/metadata
    """
    content = file_path.read_text()
    routes = []
    
    # React Router v6+ pattern
    route_pattern = re.compile(
        r'<Route\s+(?:path="([^"]*)")?\s+element=\{<(\w+)'
    )
    for m in route_pattern.finditer(content):
        routes.append(RouteDef(
            path=m.group(1) or '/',
            component=m.group(2),
            file=str(file_path),
        ))
    
    # TanStack Router / object-based routes
    obj_route_pattern = re.compile(
        r'(?:path|component)\s*:\s*[\'"](/[^\'"]*)[\'"]'
    )
    for m in obj_route_pattern.finditer(content):
        routes.append(RouteDef(
            path=m.group(1),
            component='',  # Would need context to find component name
            file=str(file_path),
            is_nested='/' in m.group(1)[1:],
        ))
    
    return routes


def extract_frontend_blueprint(repo_path: Path) -> dict[str, Any]:
    """Extract a frontend blueprint from a repository.
    
    Walks the repo for JSX/TSX files, extracts components and routes,
    and returns a structured blueprint dict.
    """
    components = []
    routes = []
    css_files = []
    api_patterns = []
    
    for ext in ('.tsx', '.jsx', '.ts', '.js'):
        for file_path in repo_path.rglob(f'*{ext}'):
            # Skip node_modules, dist, .next, etc.
            if any(skip in str(file_path) for skip in ('node_modules', 'dist', '.next', '.turbo', '__pycache__')):
                continue
            
            # Extract components from JSX/TSX files
            if ext in ('.tsx', '.jsx'):
                comps = extract_components_from_file(file_path)
                components.extend(comps)
                routes.extend(extract_routes_from_file(file_path))
            
            # Track CSS files
            if ext in ('.css', '.scss', '.less'):
                css_content = file_path.read_text()
                css_vars = re.findall(r'(--[\w-]+)\s*:', css_content)
                theme_matches = re.findall(r'\[data-theme[^\]]*\]', css_content)
                if css_vars or theme_matches:
                    css_files.append({
                        'file': str(file_path.relative_to(repo_path)),
                        'css_variables': list(set(css_vars)),
                        'has_theme_system': bool(theme_matches),
                    })
            
            # Track API call patterns in all TS/JS files
            if ext in ('.ts', '.tsx', '.js', '.jsx'):
                content = file_path.read_text()
                # find fetch/axios patterns
                for m in re.finditer(r'(?:fetch|axios\.\w+)\([^)]*[`\'"](/api/[^`\'"]+)[`\'"]', content):
                    api_patterns.append({
                        'url': m.group(1),
                        'file': str(file_path.relative_to(repo_path)),
                    })
    
    # Deduplicate API patterns
    seen = set()
    unique_api_patterns = []
    for p in api_patterns:
        if p['url'] not in seen:
            seen.add(p['url'])
            unique_api_patterns.append(p)
    
    return {
        'components': [
            {
                'name': c.name,
                'file': str(Path(c.file).relative_to(repo_path)),
                'line': c.line,
                'is_default_export': c.is_default_export,
                'props': [{'name': p.name, 'type': p.type, 'required': p.required} for p in c.props],
                'state_count': len(c.state),
                'api_calls': len(c.api_calls),
                'children': c.children_components,
                'hooks': c.hooks_used,
                'css_approach': c.css_approach,
                'tailwind_classes_count': len(c.tailwind_classes),
                'theme_vars_used': c.theme_vars_used,
            }
            for c in components
        ],
        'routes': [
            {
                'path': r.path,
                'component': r.component,
                'file': str(Path(r.file).relative_to(repo_path)),
            }
            for r in routes
        ],
        'css_files': css_files,
        'api_endpoints': unique_api_patterns,
        'summary': {
            'total_components': len(components),
            'total_routes': len(routes),
            'total_css_files': len(css_files),
            'total_api_patterns': len(unique_api_patterns),
        },
    }
