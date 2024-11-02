import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routers import main_router, ai_router, data_router
import logging
import colorlog
from config.config_manager import config

def setup_logging():
    handler = colorlog.StreamHandler()
    log_colors = config.get('logging.colors', {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    })

    handler.setFormatter(colorlog.ColoredFormatter(
        '%(asctime)s - %(log_color)s%(levelname)s%(reset)s [in %(pathname)s:%(lineno)d] - %(message)s',
        log_colors=log_colors
    ))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if config.get('app.debug') else logging.INFO)

    ignored_loggers = config.get('logging.ignored_loggers', {})
    for logger_name, level in ignored_loggers.items():
        logging.getLogger(logger_name).setLevel(getattr(logging, level))

setup_logging()

app = FastAPI()

# 配置静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置模板目录
templates = Jinja2Templates(directory="templates")

# 主页路由
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Include routers
app.include_router(main_router)
app.include_router(ai_router, prefix="/ai")
app.include_router(data_router, prefix="/data")

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=config.get('app.host', '127.0.0.1'),
        port=config.get('app.port', 5000),
        log_config=None,
        use_colors=True
    )