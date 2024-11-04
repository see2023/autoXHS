// WebSocket连接管理
const WebSocket = {
	// WebSocket实例
	connection: null,

	// 重连配置
	reconnectAttempts: 0,
	maxReconnectAttempts: 5,
	reconnectDelay: 1000,

	// 建立连接
	connect(clientId) {
		console.log('Attempting to connect WebSocket...');

		this.connection = new window.WebSocket(`ws://${window.location.host}/ws/${clientId}`);

		// 绑定事件处理器
		this.connection.onopen = this.handleOpen.bind(this);
		this.connection.onmessage = this.handleMessage.bind(this);
		this.connection.onclose = this.handleClose.bind(this, clientId);
		this.connection.onerror = this.handleError.bind(this);

		return this.connection;
	},

	// 连接建立时的处理
	handleOpen() {
		console.log('WebSocket connection opened');
		this.reconnectAttempts = 0;
	},

	// 接收消息的处理
	handleMessage(event) {
		console.log('WebSocket message received:', event.data);
		try {
			const data = JSON.parse(event.data);
			this.log('Parsed WebSocket message:', data);

			switch (data.type) {
				case 'chat_response':
					this.log('Processing chat_response:', {
						content: data.content,
						message_type: data.message_type
					});
					const shouldMerge = data.message_type === 'chat';
					Chat.appendToLastAiMessage(data.content, shouldMerge);
					break;

				case 'search_intent':
					this.log('Processing search_intent:', {
						keywords: data.keywords,
						task_id: data.task_id
					});
					Chat.handleSearchIntent(data.keywords, data.task_id);
					break;

				case 'search_task_update':
					this.log('Processing search_task_update:', {
						action: data.action,
						task_state: data.task.state,
						user_input_required: data.task.user_input_required
					});
					Task.updateTaskUI(data.task);
					break;

				case 'search_result':
					this.log('Processing search_result:', data.content);
					// 交给 Task 处理结果展示
					Task.handleSearchResult(data.content);
					break;

				default:
					this.log('Unknown message type:', data.type);
			}
		} catch (error) {
			console.error('Error processing WebSocket message:', error);
			this.log('Error details:', {
				message: error.message,
				stack: error.stack
			});
		}
	},

	// 连接关闭时的处理
	handleClose(clientId, event) {
		console.log('WebSocket connection closed:', event);

		// 尝试重连
		if (this.reconnectAttempts < this.maxReconnectAttempts) {
			this.reconnectAttempts++;
			console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
			setTimeout(() => this.connect(clientId), this.reconnectDelay);
		} else {
			console.error('Max reconnection attempts reached');
		}
	},

	// 错误处理
	handleError(error) {
		console.error('WebSocket error:', error);
	},

	// 发送消息
	send(message) {
		if (this.connection && this.connection.readyState === WebSocket.OPEN) {
			this.connection.send(JSON.stringify(message));
		} else {
			console.error('WebSocket is not connected');
		}
	},

	// 日志工具
	log(message, data) {
		console.log(`[WebSocket] ${message}`, data);
	}
}; 