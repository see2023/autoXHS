const Chat = {
	// 初始化
	init() {
		this.bindEvents();
		// 配置 marked
		marked.setOptions({
			breaks: true,  // 支持 GitHub 风格的换行
			gfm: true,     // 启用 GitHub 风格的 Markdown
			sanitize: true // 消毒 HTML 输入
		});
	},

	// 绑定事件
	bindEvents() {
		document.getElementById('userInput').addEventListener('keypress', (e) => {
			if (e.key === 'Enter' && !e.shiftKey) {
				e.preventDefault();
				this.handleInput();
			}
		});
	},

	// 处理用户输入
	async handleInput() {
		const input = document.getElementById('userInput');
		const text = input.value.trim();

		if (!text) return;

		this.addMessage('user', text);
		input.value = '';

		if (text.startsWith('搜索:') || text.startsWith('search:')) {
			const keyword = text.substring(text.indexOf(':') + 1).trim();
			await this.searchXiaohongshu(keyword);
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
					client_id: App.clientId
				})
			});

			const data = await response.json();
			if (data.status === 'error') {
				this.addMessage('ai', 'Error: ' + data.message);
			}
		} catch (error) {
			console.error('Error sending message:', error);
			this.addMessage('ai', '发送消息失败: ' + error);
		}
	},

	// 添加安全的 marked 解析函数
	safeMarkdownParse(content) {
		if (!content) return '';

		try {
			// 如果是对象，先转换为字符串
			const textContent = typeof content === 'object' ?
				JSON.stringify(content) : String(content);
			return marked.parse(textContent);
		} catch (error) {
			console.warn('Markdown parsing failed:', error);
			// 降级处理：直接返回原始内容的字符串形式
			return String(content);
		}
	},

	// 添加通用的消息解析方法
	parseMessageContent(content, contentDiv) {
		console.log('Parsing message content:', content);
		if (typeof content === 'object') {
			if (content.note_id && content.summary && content.xsec_token) {
				// 处理笔记摘要
				const note_title = content.title || '空标题';
				contentDiv.innerHTML = `
					<div class="note-summary">
						<div class="note-content" style="cursor: pointer;" 
							onclick="openNote('${content.note_id}', '${content.xsec_token}')">
							${this.safeMarkdownParse(content.summary)}
						</div>
					</div>
				`;
			} else if (content.type === 'stats') {
				// 处理统计信息
				contentDiv.innerHTML = `
					<div class="stats-summary">
						<h4>搜索统计</h4>
						<ul>
							<li>处理关键词：${content.data.keywords_processed} 个</li>
							<li>分析笔记：${content.data.total_notes} 篇</li>
							<li>收集评论：${content.data.total_comments} 条</li>
						</ul>
					</div>
				`;
			} else if (content.text) {
				// 处理带文本的对象消息
				contentDiv.innerHTML = this.safeMarkdownParse(content.text);
				if (content.html) {
					contentDiv.innerHTML += content.html;
				}
				if (content.image) {
					const img = document.createElement('img');
					img.src = `data:image/jpeg;base64,${content.image}`;
					contentDiv.appendChild(img);
				}
			} else {
				// 处理其他类型的对象消息
				contentDiv.innerHTML = this.safeMarkdownParse(content);
			}
		} else {
			// 处理普通文本消息
			contentDiv.innerHTML = this.safeMarkdownParse(content);
		}
	},

	// 添加消息
	addMessage(role, content, isHtml = false) {
		const messageDiv = document.createElement('div');
		messageDiv.className = `message ${role}-message`;

		const contentDiv = document.createElement('div');
		contentDiv.className = 'message-content';

		if (isHtml) {
			// 如果是 HTML 内容，直接设置
			contentDiv.innerHTML = content;
		} else {
			// 处理普通文本或对象消息
			this.parseMessageContent(content, contentDiv);
		}

		messageDiv.appendChild(contentDiv);
		const chatHistory = document.getElementById('chatHistory');
		chatHistory.appendChild(messageDiv);
		this.scrollToBottom();
	},

	// 追加到最后一条 AI 消息
	appendToLastAiMessage(content, shouldMerge = false) {
		console.log('Appending to last AI message:', { content, shouldMerge });

		const chatHistory = document.getElementById('chatHistory');
		const lastMessage = chatHistory.querySelector('.ai-message:last-child');

		if (shouldMerge && lastMessage) {
			const contentDiv = lastMessage.querySelector('.message-content');
			if (contentDiv) {
				if (typeof content === 'object' && content.type === 'stats') {
					// 统计信息创建新消息
					this.addMessage('ai', content);
				} else if (typeof content === 'string') {
					// 如果是字符串，解析为 markdown 并追加
					contentDiv.innerHTML += this.safeMarkdownParse(content);
				} else {
					// 其他情况，解析内容并追加
					const tempDiv = document.createElement('div');
					this.parseMessageContent(content, tempDiv);
					contentDiv.innerHTML += tempDiv.innerHTML;
				}
			}
		} else {
			// 不合并或没有最后消息时，创建新消息
			this.addMessage('ai', content);
		}

		this.scrollToBottom();
	},

	// 滚动到底部
	scrollToBottom() {
		const chatHistory = document.getElementById('chatHistory');

		chatHistory.scrollTop = chatHistory.scrollHeight;
	},

	// 处理搜索意图
	handleSearchIntent(keywords, taskId) {
		const confirmDiv = document.createElement('div');
		confirmDiv.className = 'message ai-message';
		confirmDiv.innerHTML = `
            <div class="message-content">
                <div class="search-interaction">
                    <p>看起来您想搜索关于「${keywords}」的信息。</p>
                    <div class="interaction-buttons">
                        <button class="control-button" onclick="Task.startAutoSearch('${keywords}', '${taskId}')">
                            开始智能搜索
                        </button>
                        <button class="control-button" onclick="Task.cancelAutoSearch('${taskId}')">
                            取消
                        </button>
                    </div>
                </div>
            </div>
        `;
		document.getElementById('chatHistory').appendChild(confirmDiv);
		this.scrollToBottom();
	}
}; 