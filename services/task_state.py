from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_USER_INPUT = "waiting_user_input"
    WAITING_BROWSER = "waiting_browser"
    ANALYZING = "analyzing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskEvent(Enum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    REQUIRE_INPUT = "require_input"
    RECEIVE_INPUT = "receive_input"
    COMPLETE = "complete"
    FAIL = "fail"
    PROGRESS = "progress"

class SearchProgress:
    def __init__(self):
        self.current_keyword: str = ""
        self.keywords_total: int = 0
        self.keywords_completed: int = 0
        self.notes_total: int = 0
        self.notes_processed: int = 0
        self.comments_total: int = 0
        self.comments_processed: int = 0
        self.percentage: float = 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_keyword": self.current_keyword,
            "keywords_total": self.keywords_total,
            "keywords_completed": self.keywords_completed,
            "notes_total": self.notes_total,
            "notes_processed": self.notes_processed,
            "comments_total": self.comments_total,
            "comments_processed": self.comments_processed,
            "percentage": self.percentage
        }

class SearchTask:
    def __init__(self, keywords: str, client_id: str):
        self.task_id: str = str(uuid.uuid4())
        self.keywords: str = keywords
        self.client_id: str = client_id
        self.state: TaskState = TaskState.PENDING
        self.start_time: datetime = datetime.now()
        self.end_time: Optional[datetime] = None
        self.error: Optional[str] = None
        self.results: List[Dict] = []
        self.progress: SearchProgress = SearchProgress()
        
        # 用于存储任务执行过程中的中间状态
        self.context: Dict[str, Any] = {}
        
        # 用于记录状态变化历史
        self.state_history: List[Dict[str, Any]] = []
        
        # 用于存储需要用户处理的数据
        self.user_input_required: Optional[Dict[str, Any]] = None
        
    def update_state(self, new_state: TaskState, event: TaskEvent, message: Optional[str] = None):
        """更新任务状态并记录历史"""
        old_state = self.state
        self.state = new_state
        
        state_change = {
            "timestamp": datetime.now(),
            "from_state": old_state,
            "to_state": new_state,
            "event": event,
            "message": message
        }
        self.state_history.append(state_change)
        
        if new_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
            self.end_time = datetime.now()
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典格式"""
        return {
            "task_id": self.task_id,
            "keywords": self.keywords,
            "client_id": self.client_id,
            "state": self.state.value,
            "progress": self.progress.to_dict(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error,
            "results_count": len(self.results),
            "user_input_required": self.user_input_required,
            "last_message": self.state_history[-1]["message"] if self.state_history else None
        }