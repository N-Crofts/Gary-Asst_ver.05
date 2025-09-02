from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_digest(meetings):
    template = _env.get_template("digest.html")
    return template.render(meetings=meetings)
