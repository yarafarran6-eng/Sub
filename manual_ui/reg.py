"""A registry of the screen's components by name. Handlers return {name: value} and `R` turns that into what Gradio needs,
so no handler depends on the ORDER of a long list of outputs."""
C = {}


def put(name, comp):
    C[name] = comp
    return comp


def R(**vals):
    return {C[k]: v for k, v in vals.items()}
