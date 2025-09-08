from datetime import datetime
from typing import Dict, Any

from fastapi.templating import Jinja2Templates
from starlette.requests import Request


templates = Jinja2Templates(directory="app/templates")


def render_digest_html(context: Dict[str, Any]) -> str:
    request = context.get("request")
    if request is None:
        request = Request(scope={"type": "http"})
    template = templates.get_template("digest.html")
    html = template.render({**context, "request": request})
    return html


