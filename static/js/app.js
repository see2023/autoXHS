// 全局应用状态和初始化
const App = {
	// 全局状态
	clientId: Date.now().toString(),
	ws: null,

	// 初始化应用
	async init() {
		console.log('Initializing app...');

		// 初始化WebSocket连接
		this.ws = WebSocket.connect(this.clientId);

		// 绑定输入事件
		this.bindEvents();

		// 加载现有任务
		this.loadExistingTasks();

		// 初始化浏览器
		try {
			const response = await fetch('/open_xiaohongshu');
			const data = await response.json();
			if (data.status === 'success') {
				console.log('Browser initialized');
			}
		} catch (error) {
			console.error('Error initializing browser:', error);
		}
	},

	// 绑定事件处理
	bindEvents() {
		// 输入框回车事件
		document.getElementById('userInput').addEventListener('keypress', function (e) {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				Chat.handleInput();
			}
		});
	},

	// 处理用户输入
	async handleInput() {
		const input = document.getElementById('userInput');
		const text = input.value.trim();

		if (!text) return;

		Chat.addMessage('user', text);
		input.value = '';

		if (text.startsWith('搜索:') || text.startsWith('search:')) {
			const keyword = text.substring(text.indexOf(':') + 1).trim();
			this.searchXiaohongshu(keyword);
		} else {
			await this.sendMessage(text);
		}
	},

	// 发送消息到服务器
	async sendMessage(message) {
		try {
			const response = await fetch('/ai/chat', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					message: message,
					client_id: this.clientId
				})
			});

			const data = await response.json();
			if (data.status === 'error') {
				Chat.addMessage('ai', 'Error: ' + data.message);
			}
		} catch (error) {
			console.error('Error sending message:', error);
			Chat.addMessage('ai', '发送消息失败: ' + error);
		}
	},

	// 加载现有任务
	async loadExistingTasks() {
		try {
			const response = await fetch(`/ai/search_tasks/${this.clientId}`);
			const data = await response.json();
			if (data.status === 'success') {
				data.tasks.forEach(task => this.updateTaskUI(task));
			}
		} catch (error) {
			console.error('Error loading existing tasks:', error);
		}
	},

	// 滚动到底部
	scrollToBottom() {
		const chatHistory = document.getElementById('chatHistory');
		chatHistory.scrollTop = chatHistory.scrollHeight;
	},

	// 日志工具
	log(message, data) {
		console.log(`[App] ${message}`, data);
	},

	// 搜索小红书
	async searchXiaohongshu() {
		const input = document.getElementById('userInput');
		const keyword = input.value.trim();

		if (!keyword) {
			Chat.addMessage('ai', '请输入搜索关键词');
			return;
		}

		Chat.addMessage('user', '搜索: ' + keyword);

		try {
			const response = await fetch(`/search_xiaohongshu?keyword=${encodeURIComponent(keyword)}`);
			const data = await response.json();
			if (data.status === 'success') {
				this.updateResults(data.results);
			} else {
				Chat.addMessage('ai', '搜索失败：' + (data.message || '未知错误'));
			}
		} catch (error) {
			console.error('Search error:', error);
			Chat.addMessage('ai', '搜索出错：' + error);
		}

		input.value = '';
	},

	// 打开小红书
	async openXiaohongshu() {
		Chat.addMessage('user', '打开小红书');
		try {
			const response = await fetch('/open_xiaohongshu');
			const data = await response.json();
			Chat.addMessage('ai', data.message);
		} catch (error) {
			Chat.addMessage('ai', '打开小红书失败: ' + error);
		}
	},

	// 测试浏览器
	async testBrowser() {
		Chat.addMessage('user', '测试浏览器');
		try {
			const response = await fetch('/test_browser');
			const data = await response.json();
			if (data.status === 'success') {
				// 分开显示OCR文本和截图
				let content = {
					text: '识别文本：' + (data.ocr_text || '无文本'),
					image: data.image
				};
				Chat.addMessage('ai', content);
			} else {
				Chat.addMessage('ai', '测试浏览器失败：' + (data.message || '未知错误'));
			}
		} catch (error) {
			Chat.addMessage('ai', '测试浏览器失败: ' + error);
		}
	},

	// 更新搜索结果
	updateResults(results) {
		const resultsHTML = `
			<div class="search-results-grid">
				${results.map(result => `
					<div class="result-item" data-id="${result.id}" data-xsec-token="${result.xsec_token}">
						<h3 style="cursor: pointer;" onclick="openNote('${result.id}', '${result.xsec_token}')">${result.title}</h3>
						<p>${result.nickname}</p>
						<div class="result-meta">
							<span>点赞: ${result.liked_count}</span>
						</div>
					</div>
				`).join('')}
			</div>
		`;
		Chat.addMessage('ai', resultsHTML, true);
	}
};

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => App.init());

// Add this method to handle note clicks
async function openNote(noteId, xsecToken) {
	try {
		const response = await fetch('/open_note', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				note_id: noteId,
				xsec_token: xsecToken
			})
		});
		const data = await response.json();
		if (data.status !== 'success') {
			console.error('打开笔记失败：' + data.message);
			alert('打开笔记失败：' + data.message);
		}
	} catch (error) {
		console.error('Error opening note:', error);
		Chat.addMessage('ai', '打开笔记出错：' + error);
	}
} 