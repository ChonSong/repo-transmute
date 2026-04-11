// goast — Go AST extractor for RepoTransmute
// Parses a .go file and emits JSON representation of functions, structs, and interfaces.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"sort"
	"strings"
)

type FuncOutput struct {
	Name      string `json:"name"`
	Signature string `json:"signature"`
	Line      int    `json:"line"`
	Doc       string `json:"doc,omitempty"`
	IsMethod  bool   `json:"is_method"`
	Receiver  string `json:"receiver,omitempty"`
}

type FieldOutput struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

type StructOutput struct {
	Name   string        `json:"name"`
	Line   int           `json:"line"`
	Doc    string        `json:"doc,omitempty"`
	Fields []FieldOutput `json:"fields"`
}

type MethodOutput struct {
	Name      string `json:"name"`
	Signature string `json:"signature"`
}

type InterfaceOutput struct {
	Name    string         `json:"name"`
	Line    int           `json:"line"`
	Doc     string        `json:"doc,omitempty"`
	Methods []MethodOutput `json:"methods"`
}

type Output struct {
	Functions  []FuncOutput        `json:"functions"`
	Structs    []StructOutput      `json:"structs"`
	Interfaces []InterfaceOutput   `json:"interfaces"`
}

func typeString(t ast.Expr) string {
	switch v := t.(type) {
	case *ast.Ident:
		return v.Name
	case *ast.SelectorExpr:
		return typeString(v.X) + "." + v.Sel.Name
	case *ast.StarExpr:
		return "*" + typeString(v.X)
	case *ast.ArrayType:
		if v.Len == nil {
			return "[]" + typeString(v.Elt)
		}
		return "[...]" + typeString(v.Elt)
	case *ast.MapType:
		return "map[" + typeString(v.Key) + "]" + typeString(v.Value)
	case *ast.ChanType:
		return "chan " + typeString(v.Value)
	case *ast.FuncType:
		return "func" + typeStringFunc(v)
	case *ast.InterfaceType:
		return "interface{}"
	case *ast.StructType:
		return "struct{}"
	case *ast.Ellipsis:
		return "..." + typeString(v.Elt)
	case *ast.IndexExpr:
		return typeString(v.X) + "[" + typeString(v.Index) + "]"
	case *ast.IndexListExpr:
		types := make([]string, len(v.Indices))
		for i, idx := range v.Indices {
			types[i] = typeString(idx)
		}
		return typeString(v.X) + "[" + strings.Join(types, ", ") + "]"
	default:
		return "any"
	}
}

func typeStringFunc(t *ast.FuncType) string {
	params := paramListString(t.Params)
	results := ""
	if t.Results != nil {
		results = " " + paramListString(t.Results)
	}
	return "(" + params + ")" + results
}

func paramListString(list *ast.FieldList) string {
	if list == nil {
		return ""
	}
	var parts []string
	for _, p := range list.List {
		if len(p.Names) == 0 {
			parts = append(parts, typeString(p.Type))
		} else if len(p.Names) == 1 {
			parts = append(parts, typeString(p.Type))
		} else {
			var names []string
			for _, n := range p.Names {
				names = append(names, n.Name)
			}
			parts = append(parts, strings.Join(names, ", ")+" "+typeString(p.Type))
		}
	}
	return strings.Join(parts, ", ")
}

func fieldListString(fl *ast.FieldList) string {
	if fl == nil {
		return ""
	}
	var parts []string
	for _, f := range fl.List {
		var names []string
		for _, n := range f.Names {
			names = append(names, n.Name)
		}
		if len(names) == 0 {
			parts = append(parts, typeString(f.Type))
		} else {
			parts = append(parts, strings.Join(names, ", ")+" "+typeString(f.Type))
		}
	}
	return strings.Join(parts, ", ")
}

func receiverString(f *ast.FuncDecl) string {
	if f.Recv == nil || len(f.Recv.List) == 0 {
		return ""
	}
	return fieldListString(f.Recv)
}

// collectInterfaceTypes builds a map of interface name -> *ast.InterfaceType for all
// interface types declared in the file. This is needed to resolve embedded interface
// references (e.g., "type ReadWriter interface { Reader }") where Reader is an
// *ast.Ident that must be looked up in the file's type declarations.
func collectInterfaceTypes(file *ast.File) map[string]*ast.InterfaceType {
	result := make(map[string]*ast.InterfaceType)
	for _, decl := range file.Decls {
		d, ok := decl.(*ast.GenDecl)
		if !ok || d.Tok != token.TYPE {
			continue
		}
		for _, spec := range d.Specs {
			ts, ok := spec.(*ast.TypeSpec)
			if !ok {
				continue
			}
			if it, ok := ts.Type.(*ast.InterfaceType); ok {
				result[ts.Name.Name] = it
			}
		}
	}
	return result
}

// extractMethodsFromInterface extracts all methods from an interface type.
// If embedded is true, it recursively collects methods from embedded interfaces
// (avoiding infinite loops via the visited set).
func extractMethodsFromInterface(iface *ast.InterfaceType, ifaceTypes map[string]*ast.InterfaceType, visited map[string]bool) []MethodOutput {
	var methods []MethodOutput
	if iface.Methods == nil {
		return methods
	}
	for _, m := range iface.Methods.List {
		if len(m.Names) == 0 {
			// Embedded interface: could be *ast.InterfaceType (inline) or *ast.Ident (reference)
			switch t := m.Type.(type) {
			case *ast.InterfaceType:
				// Inline anonymous interface e.g. interface { interface { Read() } }
				// Recursively collect from the inline type
				embeddedName := "_embedded_" + fmt.Sprintf("%p", t)
				if !visited[embeddedName] {
					visited[embeddedName] = true
					methods = append(methods, extractMethodsFromInterface(t, ifaceTypes, visited)...)
				}
			case *ast.Ident:
				// Reference to a named interface defined elsewhere in the file
				if embeddedIface, ok := ifaceTypes[t.Name]; ok {
					if !visited[t.Name] {
						visited[t.Name] = true
						methods = append(methods, extractMethodsFromInterface(embeddedIface, ifaceTypes, visited)...)
						visited[t.Name] = false
					}
				}
			}
			continue
		}
		// Named method
		mname := m.Names[0].Name
		msig := ""
		if m.Type != nil {
			if ft, ok := m.Type.(*ast.FuncType); ok {
				msig = typeStringFunc(ft)
			}
		}
		methods = append(methods, MethodOutput{
			Name:      mname,
			Signature: msig,
		})
	}
	return methods
}

func extractFuncsAndMethods(file *ast.File) ([]FuncOutput, []StructOutput, []InterfaceOutput) {
	var funcs []FuncOutput
	var structs []StructOutput
	var interfaces []InterfaceOutput

	seenFuncs := make(map[string]bool)

	// Collect all interface types for embedded interface resolution
	ifaceTypes := collectInterfaceTypes(file)

	for _, decl := range file.Decls {
		switch d := decl.(type) {
		case *ast.FuncDecl:
			if d.Name.Name == "_" {
				continue
			}
			key := d.Name.Name
			if d.Recv != nil && len(d.Recv.List) > 0 {
				key = receiverString(d) + "." + d.Name.Name
			}
			if seenFuncs[key] {
				continue
			}
			seenFuncs[key] = true

			sig := ""
			if d.Type.Params != nil {
				sig = "(" + fieldListString(d.Type.Params) + ")"
			}
			if d.Type.Results != nil {
				res := fieldListString(d.Type.Results)
				if res != "" {
					sig += " " + res
				}
			}

			var doc string
			if d.Doc != nil {
				doc = d.Doc.Text()
			}

			funcs = append(funcs, FuncOutput{
				Name:      d.Name.Name,
				Signature: sig,
				Line:      int(fset.Position(d.Pos()).Line),
				Doc:       doc,
				IsMethod:  d.Recv != nil && len(d.Recv.List) > 0,
				Receiver:  receiverString(d),
			})

		case *ast.GenDecl:
			if d.Tok == token.TYPE {
				for _, spec := range d.Specs {
					ts := spec.(*ast.TypeSpec)
					var doc string
					if d.Doc != nil {
						doc = d.Doc.Text()
					}
					line := int(fset.Position(ts.Pos()).Line)

					switch v := ts.Type.(type) {
					case *ast.StructType:
						var fields []FieldOutput
						if v.Fields != nil {
							for _, f := range v.Fields.List {
								var fname string
								if len(f.Names) == 0 {
									fname = "_"
								} else {
									var names []string
									for _, n := range f.Names {
										names = append(names, n.Name)
									}
									fname = strings.Join(names, ", ")
								}
								fields = append(fields, FieldOutput{
									Name: fname,
									Type: typeString(f.Type),
								})
							}
						}
						structs = append(structs, StructOutput{
							Name:   ts.Name.Name,
							Line:   line,
							Doc:    doc,
							Fields: fields,
						})

					case *ast.InterfaceType:
						visited := make(map[string]bool)
						methods := extractMethodsFromInterface(v, ifaceTypes, visited)
						interfaces = append(interfaces, InterfaceOutput{
							Name:    ts.Name.Name,
							Line:    line,
							Doc:     doc,
							Methods: methods,
						})
					}
				}
			}
		}
	}

	// Sort by line number for stable output
	sort.Slice(funcs, func(i, j int) bool { return funcs[i].Line < funcs[j].Line })
	sort.Slice(structs, func(i, j int) bool { return structs[i].Line < structs[j].Line })
	sort.Slice(interfaces, func(i, j int) bool { return interfaces[i].Line < structs[j].Line })

	return funcs, structs, interfaces
}

var fset = token.NewFileSet()

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: goast <file.go>")
		os.Exit(1)
	}

	filename := os.Args[1]
	file, err := parser.ParseFile(fset, filename, nil, parser.ParseComments)
	if err != nil {
		fmt.Fprintf(os.Stderr, "parse error: %v\n", err)
		out, _ := json.Marshal(Output{})
		fmt.Println(string(out))
		return
	}

	funcs, structs, interfaces := extractFuncsAndMethods(file)

	out := Output{
		Functions:  funcs,
		Structs:    structs,
		Interfaces: interfaces,
	}

	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "json error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(data))
}
