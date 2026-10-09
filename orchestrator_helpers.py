import ast

def get_function_source(filename, func_name):
    with open(filename, 'r') as f:
        source = f.read()
    
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lines = source.split('\n')
            # Extract lines corresponding to the function
            start = node.lineno - 1
            end = node.end_lineno
            return '\n'.join(lines[start:end])
    return None

def replace_function_source(filename, func_name, new_func_source):
    with open(filename, 'r') as f:
        source = f.read()
        
    old_func_source = get_function_source(filename, func_name)
    if not old_func_source:
        return False
        
    new_source = source.replace(old_func_source, new_func_source.strip())
    with open(filename, 'w') as f:
        f.write(new_source)
    return True
