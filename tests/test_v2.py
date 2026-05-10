"""Tests for repo-transmute v2 modules."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from repo_transmute.v2.models import (
    ComponentDef, RouteDef, Framework, StyleApproach,
    ComponentType, MigrationStatus, TargetStack,
    PropDef, StateDef, ImportDef, APICallDef,
    ProjectBlueprint, StyleSystem, ThemeDef
)
from repo_transmute.v2.ingest.detector import detect_framework, FRAMEWORK_SIGNALS
from repo_transmute.v2.ingest.walker import walk_project, SKIP_DIRS
from repo_transmute.v2.extract.ast_extractor import extract_components_ast
from repo_transmute.v2.migrate.style_mapper import map_styles


class TestModels(unittest.TestCase):
    """Test data models."""
    
    def test_component_def_creation(self):
        comp = ComponentDef(
            name='TestComponent',
            file='src/components/test.tsx',
            line=1,
            component_type=ComponentType.COMPONENT,
        )
        self.assertEqual(comp.name, 'TestComponent')
        self.assertEqual(comp.component_type, ComponentType.COMPONENT)
        self.assertEqual(comp.migration_status, MigrationStatus.PENDING)
    
    def test_project_blueprint(self):
        bp = ProjectBlueprint(
            source_repo='test/repo',
            source_path=Path('/tmp/test'),
            framework=Framework.REACT,
            style_approach=StyleApproach.TAILWIND,
        )
        self.assertEqual(bp.component_count, 0)
        self.assertEqual(bp.page_count, 0)
        self.assertIsNone(bp.get_component('nonexistent'))
    
    def test_style_system(self):
        system = StyleSystem(
            approach=StyleApproach.TAILWIND,
            themes=[ThemeDef(name='dark', is_dark=True)],
            css_variables={'--color-primary': '#3B82F6'},
        )
        self.assertEqual(len(system.themes), 1)
        self.assertEqual(system.css_variables['--color-primary'], '#3B82F6')


class TestDetector(unittest.TestCase):
    """Test framework detection."""
    
    def test_framework_signals_exist(self):
        self.assertIn(Framework.REACT, FRAMEWORK_SIGNALS)
        self.assertIn(Framework.VUE, FRAMEWORK_SIGNALS)
        self.assertIn(Framework.SVELTE, FRAMEWORK_SIGNALS)
    
    def test_detect_hermes_workspace(self):
        framework, style = detect_framework(Path('/opt/data/hermes-workspace'))
        self.assertEqual(framework, Framework.REACT)
        self.assertEqual(style, StyleApproach.TAILWIND)
    
    def test_detect_agent_os(self):
        framework, style = detect_framework(Path('/opt/data/agent-os'))
        self.assertEqual(framework, Framework.REACT)
        self.assertIn(style, [StyleApproach.CSS_VARIABLES, StyleApproach.TAILWIND])


class TestWalker(unittest.TestCase):
    """Test file walking."""
    
    def test_skip_dirs(self):
        self.assertIn('node_modules', SKIP_DIRS)
        self.assertIn('.git', SKIP_DIRS)
    
    def test_walk_hermes_workspace(self):
        result = walk_project(Path('/opt/data/hermes-workspace'), Framework.REACT)
        self.assertIsInstance(result, dict)
        self.assertIn('components', result)
        self.assertIn('pages', result)
        self.assertIn('styles', result)
        self.assertGreater(len(result['components']), 0)


class TestASTExtractor(unittest.TestCase):
    """Test AST extraction."""
    
    def test_extract_components_from_hermes_workspace(self):
        """Test that we can extract components from the real hermes-workspace."""
        components = extract_components_ast(
            Path('/opt/data/hermes-workspace'),
            Framework.REACT,
        )
        self.assertGreater(len(components), 0)
        # Check that components have expected fields
        comp = components[0]
        self.assertIsInstance(comp, ComponentDef)
        self.assertTrue(comp.name)
        self.assertTrue(comp.file)


class TestStyleMapper(unittest.TestCase):
    """Test style mapping."""
    
    def test_map_tailwind_to_css_vars(self):
        source = StyleSystem(
            approach=StyleApproach.TAILWIND,
            css_variables={'--color-primary': '#3B82F6'},
        )
        mapping = map_styles(source, StyleApproach.CSS_VARIABLES)
        self.assertEqual(mapping['source_approach'], 'tailwind')
        self.assertEqual(mapping['target_approach'], 'css-variables')
    
    def test_map_css_vars_to_tailwind(self):
        source = StyleSystem(
            approach=StyleApproach.CSS_VARIABLES,
            css_variables={'--color-primary': '#3B82F6'},
        )
        mapping = map_styles(source, StyleApproach.TAILWIND)
        self.assertIn('color_mapping', mapping)
        self.assertIn('variable_mapping', mapping)


class TestMigrationOrder(unittest.TestCase):
    """Test migration order computation."""
    
    def test_compute_migration_order(self):
        from repo_transmute.v2.cli import _compute_migration_order
        
        bp = ProjectBlueprint(
            source_repo='test/repo',
            source_path=Path('/tmp/test'),
            framework=Framework.REACT,
            style_approach=StyleApproach.TAILWIND,
            components=[
                ComponentDef(name='Button', file='button.tsx', line=1),
                ComponentDef(name='Form', file='form.tsx', line=1, children_components=['Button', 'Input']),
                ComponentDef(name='Input', file='input.tsx', line=1),
            ],
            dependencies={
                'Button': [],
                'Input': [],
                'Form': ['Button', 'Input'],
            },
        )
        
        order = _compute_migration_order(bp)
        # Button and Input should come before Form
        form_idx = order.index('Form')
        button_idx = order.index('Button')
        input_idx = order.index('Input')
        self.assertLess(button_idx, form_idx)
        self.assertLess(input_idx, form_idx)


if __name__ == '__main__':
    unittest.main()
