from fastapi import APIRouter, Request, Query, WebSocket, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from services.browser_service import BrowserService
from services.websocket_service import WebsocketService
import logging
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
browser_service = BrowserService()
websocket_service = WebsocketService()

# 首页路由
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        if browser_service.driver is None:
            logger.info("Starting browser...")
            await browser_service.start_browser()
            logger.info("Opening xiaohongshu...")
            await browser_service.open_xiaohongshu()
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)

@router.get("/open_xiaohongshu")
async def open_xiaohongshu():
    try:
        success = await browser_service.open_xiaohongshu()
        return {
            'status': 'success' if success else 'error',
            'message': 'Successfully opened Xiaohongshu' if success else 'Failed to open Xiaohongshu'
        }
    except Exception as e:
        logger.error(f"Error in open_xiaohongshu: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }

@router.get("/test_browser")
async def test_browser():
    try:
        result = await browser_service.scroll_screenshot_and_ocr()
        return result
    except Exception as e:
        logger.error(f"Error in test_browser: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }

@router.get("/search_xiaohongshu")
async def search_xiaohongshu(keyword: str):
    try:
        results = await browser_service.search_xiaohongshu(keyword)
        return results
    except Exception as e:
        logger.error(f"Error in search_xiaohongshu: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }

@router.post("/open_note")
async def open_note(
    note_id: str = Body(...),
    xsec_token: str = Body(...)
):
    try:
        result = await browser_service.open_note(note_id, xsec_token)
        return result
    except Exception as e:
        logger.error(f"Error opening note: {e}")
        return {"status": "error", "message": str(e)}

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    logger.info(f"New WebSocket connection request from client {client_id}")
    await websocket_service.connect(client_id, websocket)
    logger.info(f"Client {client_id} connected, connection id: {id(websocket)}")
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received message from client {client_id}: {data}")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        logger.info(f"Client {client_id} disconnected")
        websocket_service.disconnect(client_id)