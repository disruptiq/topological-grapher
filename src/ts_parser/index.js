import tsMorph from 'ts-morph';
const { Project, SyntaxKind, Symbol, Node: TsNode, ts } = tsMorph;
import path from 'path';

// --- Enums to match Python Pydantic models ---
const NodeType = {
    FILE: "file",
    CLASS: "class",
    FUNCTION: "function",
    VARIABLE: "variable",
    INTERFACE: "interface",
    TYPE: "type",
    ENUM: "enum",
    NAMESPACE: "namespace",
};

const EdgeType = {
    CONTAINS: "contains",
    IMPORTS: "imports",
    CALLS: "calls",
    INHERITS: "inherits",
    IMPLEMENTS: "implements",
    USES_TYPE: "uses_type",
    USES_VARIABLE: "uses_variable",
};

// --- Helper Functions ---

/**
 * Generates a unique, qualified ID for a given declaration node.
 * @param {import('ts-morph').Node} node - The declaration node.
 * @returns {string|null} The unique ID or null if it cannot be generated.
 */
function generateNodeId(node, rootPath) {
    if (!node || node.isKind(SyntaxKind.SourceFile)) {
        const filePath = node?.getFilePath();
        if (!filePath) return null;
        return path.relative(rootPath, filePath).replace(/\\/g, '/');
    }
    const sourceFile = node.getSourceFile();
    const filePath = sourceFile.getFilePath();
    const relativePath = path.relative(rootPath, filePath).replace(/\\/g, '/');

    let name = '';
    // Special handling for constructors
    if (TsNode.isConstructorDeclaration(node)) {
        name = 'constructor';
    } else if (TsNode.isNamed(node)) {
        name = node.getName();
    }
    
    if (!name && TsNode.isVariableDeclaration(node)) name = node.getName();

    // Handle anonymous default exports
    if (!name && TsNode.isExportable(node) && node.isDefaultExport()) {
        name = '::default';
    }

    if (!name) return null;

    const baseName = name; // The simple name without overload index.

    // Handle function overloads by appending a unique index to the ID part
    if (TsNode.isFunctionDeclaration(node) || TsNode.isMethodDeclaration(node) || TsNode.isConstructorDeclaration(node)) {
        try {
            const symbol = node.getSymbol();
            if (symbol) {
                const declarations = symbol.getDeclarations();
                if (declarations.length > 1) {
                    // Find index based on position, which is more reliable than object equality.
                    const index = declarations.findIndex(d => d.getStart() === node.getStart() && d.getEnd() === node.getEnd());
                    if (index !== -1) {
                        name = `${baseName}:${index}`; // Append index to the name for the ID
                    }
                }
            }
        } catch (e) {
            // Failsafe for symbols that might not resolve
        }
    }

    const ancestors = node.getAncestors();
    const qualifiedParts = [];

    for (const ancestor of ancestors) {
        if (TsNode.isClassDeclaration(ancestor) || TsNode.isInterfaceDeclaration(ancestor) || TsNode.isModuleDeclaration(ancestor)) {
            qualifiedParts.unshift(ancestor.getName());
        }
    }
    qualifiedParts.push(name);
    return `${relativePath}__${qualifiedParts.join('.')}`;
}


/**
 * Checks if a symbol's declaration is within the project's root path and not in node_modules.
 * @param {Symbol|undefined} symbol - The symbol to check.
 * @param {string} rootPath - The absolute path to the project root.
 * @returns {import('ts-morph').Node|null} The declaration node if it's internal, otherwise null.
 */
function getInternalDeclaration(symbol, rootPath) {
    if (!symbol) return null;
    const declaration = symbol.getDeclarations()[0];
    if (!declaration) return null;

    const sourceFile = declaration.getSourceFile();
    const filePath = sourceFile.getFilePath();

    const isInternal = filePath.startsWith(rootPath) && !filePath.includes('node_modules');
    return isInternal ? declaration : null;
}

// --- Main Parsing Logic ---

async function main() {
    try {
        const args = process.argv.slice(2);
        let filePath = args[args.indexOf('--filePath') + 1];
        let rootPath = args[args.indexOf('--rootPath') + 1];
        let tsconfigPath = args[args.indexOf('--tsconfigPath') + 1];

        // --- Path Normalization for Windows ---
        if (path.sep === '\\') {
            if (filePath) filePath = filePath.replace(/\\/g, '/');
            if (rootPath) rootPath = rootPath.replace(/\\/g, '/');
            if (tsconfigPath) tsconfigPath = tsconfigPath.replace(/\\/g, '/');
        }

        if (!filePath || !rootPath || !tsconfigPath) {
            console.error('Usage: node index.js --filePath <path> --rootPath <path> --tsconfigPath <path>');
            process.exit(1);
        }

        const project = new Project({ tsConfigFilePath: tsconfigPath });
        const sourceFile = project.getSourceFileOrThrow(filePath);

        const nodes = [];
        const edges = [];
        const discoveredIds = new Set();
        const dynamicScopeIds = new Set();

        const addNode = (nodeData) => {
            if (nodeData.id && !discoveredIds.has(nodeData.id)) {
                nodes.push(nodeData);
                discoveredIds.add(nodeData.id);
            }
        };

        const addEdge = (edgeData) => {
            if (edgeData.source && edgeData.target) {
                edges.push(edgeData);
            }
        };

        // --- Pass 1: Node Discovery & Containment ---
        const absoluteFileId = sourceFile.getFilePath();
        const fileId = path.relative(rootPath, absoluteFileId).replace(/\\/g, '/');
        addNode({
            id: fileId,
            type: NodeType.FILE,
            name: path.basename(fileId),
            metadata: { file_path: fileId, start_line: 1, end_line: sourceFile.getEndLineNumber() }
        });

        sourceFile.forEachDescendant((node) => {
            const parentId = generateNodeId(node.getParent());
            let nodeType = null;
            let nodeName = '';

            if (TsNode.isClassDeclaration(node)) nodeType = NodeType.CLASS;
            else if (TsNode.isFunctionDeclaration(node)) nodeType = NodeType.FUNCTION;
            else if (TsNode.isInterfaceDeclaration(node)) nodeType = NodeType.INTERFACE;
            else if (TsNode.isEnumDeclaration(node)) nodeType = NodeType.ENUM;
            else if (TsNode.isTypeAliasDeclaration(node)) nodeType = NodeType.TYPE;
            else if (TsNode.isModuleDeclaration(node)) nodeType = NodeType.NAMESPACE;
            else if (TsNode.isVariableDeclaration(node)) {
                const initializer = node.getInitializer();
                if (initializer && (TsNode.isArrowFunction(initializer) || TsNode.isFunctionExpression(initializer))) {
                    nodeType = NodeType.FUNCTION;
                } else if (node.getFirstAncestorByKind(SyntaxKind.FunctionDeclaration) === undefined) {
                    nodeType = NodeType.VARIABLE;
                }
            }
            else if (TsNode.isMethodDeclaration(node)) nodeType = NodeType.FUNCTION;
            else if (TsNode.isPropertyDeclaration(node)) nodeType = NodeType.VARIABLE;
            else if (TsNode.isConstructorDeclaration(node)) nodeType = NodeType.FUNCTION;

            if (nodeType) {
                // Centralized name-finding logic, keeping the display name simple.
                if (TsNode.isConstructorDeclaration(node)) {
                    nodeName = 'constructor';
                } else if (TsNode.isNamed(node)) {
                    nodeName = node.getName();
                }
                
                if (!nodeName && TsNode.isVariableDeclaration(node)) {
                    nodeName = node.getName();
                }
                
                if (!nodeName && TsNode.isExportable(node) && node.isDefaultExport()) {
                    nodeName = '::default';
                }

                const nodeId = generateNodeId(node, rootPath);
                addNode({
                    id: nodeId,
                    type: nodeType,
                    name: nodeName,
                    metadata: { file_path: fileId, start_line: node.getStartLineNumber(), end_line: node.getEndLineNumber() }
                });
            }
        });

        // --- Pass 2: Dependency Discovery ---
        function discoverAndLink(node, scopeStack) {
            const currentScopeId = scopeStack[scopeStack.length - 1];
            let nodeId = null;

            // Find the corresponding node from Pass 1 to establish its ID.
            const nodeNamePart = generateNodeId(node, rootPath)?.split(':').pop();
            const foundNode = nodes.find(n => 
                n.metadata.start_line === node.getStartLineNumber() && 
                n.id.endsWith(nodeNamePart || '___impossible___')
            );
            
            if (foundNode) {
                nodeId = foundNode.id;
                // Create the CONTAINS edge using the correct parent from the scope stack.
                if (currentScopeId !== nodeId) {
                    addEdge({ source: currentScopeId, target: nodeId, type: EdgeType.CONTAINS });
                }
            }

            // --- Find Dependencies FROM the current scope ---
            // IMPORTS
            if (TsNode.isImportDeclaration(node)) {
                const targetFile = node.getModuleSpecifierSourceFile();
                if (targetFile && getInternalDeclaration(targetFile.getSymbol(), rootPath)) {
                    const targetFileId = path.relative(rootPath, targetFile.getFilePath()).replace(/\\/g, '/');
                    addEdge({ source: fileId, target: targetFileId, type: EdgeType.IMPORTS });
                }
            }

            // INHERITS / IMPLEMENTS
            if (TsNode.isClassDeclaration(node)) {
                const classId = generateNodeId(node, rootPath);
                const baseClass = node.getBaseClass();
                const baseClassDecl = getInternalDeclaration(baseClass?.getSymbol(), rootPath);
                if (baseClassDecl) {
                    addEdge({ source: classId, target: generateNodeId(baseClassDecl, rootPath), type: EdgeType.INHERITS });
                }
                node.getImplements().forEach(impl => {
                    const implDecl = getInternalDeclaration(impl.getExpression().getSymbol(), rootPath);
                    if (implDecl) {
                        addEdge({ source: classId, target: generateNodeId(implDecl, rootPath), type: EdgeType.IMPLEMENTS });
                    }
                });
            }

            // CALLS, require() IMPORTS, and dynamic import()
            if (TsNode.isCallExpression(node)) {
                const expression = node.getExpression();
                if (expression.isKind(SyntaxKind.ImportKeyword)) {
                    dynamicScopeIds.add(currentScopeId);
                } else if (TsNode.isIdentifier(expression) && expression.getText() === 'require' && node.getArguments().length === 1) {
                    const decl = getInternalDeclaration(node.getResolvedSignature()?.getDeclaration()?.getSymbol(), rootPath);
                    if (decl && TsNode.isSourceFile(decl)) {
                        const targetFileId = path.relative(rootPath, decl.getFilePath()).replace(/\\/g, '/');
                        addEdge({ source: fileId, target: targetFileId, type: EdgeType.IMPORTS });
                    }
                } else {
                    const decl = getInternalDeclaration(expression.getSymbol(), rootPath);
                    if (decl) {
                        addEdge({ source: currentScopeId, target: generateNodeId(decl, rootPath), type: EdgeType.CALLS });
                    }
                }
            }

            // USES_TYPE
            if (TsNode.isTyped(node) && node.getTypeNode()) {
                node.getTypeNode().forEachDescendant((typeNode) => {
                    if (TsNode.isIdentifier(typeNode) || TsNode.isPropertyAccessExpression(typeNode)) {
                         const decl = getInternalDeclaration(typeNode.getSymbol(), rootPath);
                         if(decl) {
                             addEdge({ source: currentScopeId, target: generateNodeId(decl, rootPath), type: EdgeType.USES_TYPE });
                         }
                    }
                });
            }
            
            // USES_VARIABLE
            if (TsNode.isPropertyAccessExpression(node) || TsNode.isIdentifier(node)) {
                const parent = node.getParent();
                const isHandledElsewhere = 
                    ts.isDeclaration(parent.compilerNode) ||
                    (TsNode.isPropertyAccessExpression(node) ? false : parent.isKind(SyntaxKind.PropertyAccessExpression)) ||
                    (parent.isKind(SyntaxKind.CallExpression) && parent.getExpression() === node) ||
                    !!node.getAncestors().find(a => TsNode.isTypeNode(a));
                
                if (!isHandledElsewhere) {
                    const decl = getInternalDeclaration(node.getSymbol(), rootPath);
                    if (decl && (TsNode.isVariableDeclaration(decl) || TsNode.isPropertyDeclaration(decl) || TsNode.isEnumMember(decl))) {
                        addEdge({ source: currentScopeId, target: generateNodeId(decl, rootPath), type: EdgeType.USES_VARIABLE });
                    }
                }
            }

            // --- Recurse on children with the correct new scope ---
            let nextScopeStack = scopeStack;
            let isNewScope = false;
            
            // Check if the current node defines a new scope we want to track.
            if (TsNode.isFunctionDeclaration(node) || TsNode.isMethodDeclaration(node) || TsNode.isClassDeclaration(node) || TsNode.isConstructorDeclaration(node) || TsNode.isModuleDeclaration(node)) {
                isNewScope = true;
            } else if (TsNode.isVariableDeclaration(node) && node.getInitializer()?.isKind(SyntaxKind.ArrowFunction)) {
                isNewScope = true;
            }

            if (isNewScope) {
                const newScopeId = generateNodeId(node, rootPath);
                if (newScopeId) {
                    nextScopeStack = [...scopeStack, newScopeId];
                }
            }
            node.forEachChild(child => discoverAndLink(child, nextScopeStack));
        }

        discoverAndLink(sourceFile, [fileId]);
        
        console.log(JSON.stringify({ nodes, edges, dynamicScopeIds: Array.from(dynamicScopeIds) }, null, 2));

    } catch (error) {
        console.error(error.stack);
        process.exit(1);
    }
}

main();
