from datetime import datetime

from fastapi import FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes import router
from app.services import NotFound

app = FastAPI()
app.include_router(router)
ENCODERS_BY_TYPE[datetime] = str


@app.exception_handler(RequestValidationError)
def invalid(_, exc):
    """Ошибка валидации: 400 с именем поля или параметра."""
    loc = exc.errors()[0]["loc"]
    kind = "field" if loc[0] == "body" else "parameter"
    name = loc[-1] if isinstance(loc[-1], str) else "body"
    return JSONResponse({"message": f'invalid "{name}" {kind}'}, 400)


@app.exception_handler(NotFound)
def not_found(_, exc):
    """Сущность не найдена: 404."""
    return JSONResponse({"message": "Not found"}, 404)
