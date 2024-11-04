const Task = {
	// 初始化
	init() {
		this.loadExistingTasks();
	},

	// 加载现有任务
	async loadExistingTasks() {
		try {
			const response = await fetch(`/ai/search_tasks/${App.clientId}`);
			const data = await response.json();
			if (data.status === 'success') {
				data.tasks.forEach(task => this.updateTaskUI(task));
			}
		} catch (error) {
			console.error('Error loading existing tasks:', error);
		}
	},

	// 开始自动搜索
	async startAutoSearch(keywords, taskId) {
		const normalizedKeywords = keywords.trim();
		console.log('Starting search for keywords:', normalizedKeywords, 'taskId:', taskId);

		try {
			const response = await fetch('/ai/start_auto_search', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					keywords: normalizedKeywords,
					client_id: App.clientId,
					task_id: taskId
				})
			});

			const data = await response.json();
			if (data.status === 'success') {
				Chat.addMessage('ai', '已开始智能搜索任务，我会持续为您分析相关信息...');
			} else {
				Chat.addMessage('ai', data.message || '启动搜索任务失败');
			}
		} catch (error) {
			console.error('Start auto search error:', error);
			Chat.addMessage('ai', '启动搜索任务出错：' + error);
		}
	},

	// 取消自动搜索
	async cancelAutoSearch(taskId) {
		try {
			const response = await fetch('/ai/cancel_auto_search', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					task_id: taskId,
					client_id: App.clientId
				})
			});

			const data = await response.json();
			if (data.status === 'error') {
				Chat.addMessage('ai', '取消任务失败：' + data.message);
			} else {
				const taskElement = document.getElementById(`task-${taskId}`);
				if (taskElement) {
					taskElement.remove();
				}
				Chat.addMessage('ai', '已取消任务');
			}
		} catch (error) {
			console.error('Cancel auto search error:', error);
			Chat.addMessage('ai', '取消任务出错：' + error);
		}
	},

	// 提交用户输入
	async submitUserInput(taskId, continueSearch) {
		try {
			const response = await fetch('/ai/submit_user_input', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					task_id: taskId,
					client_id: App.clientId,
					input: {
						continue_search: continueSearch
					}
				})
			});

			const data = await response.json();
			if (data.status === 'success') {
				// Chat.addMessage('user', `选择：${continueSearch ? '继续搜索' : '查看结果'}`);
			} else {
				Chat.addMessage('ai', '提交选择失败：' + data.message);
			}
		} catch (error) {
			console.error('Submit user input error:', error);
			Chat.addMessage('ai', '提交选择出错：' + error);
		}
	},

	// 更新任务UI
	updateTaskUI(task) {
		console.log('Updating task UI:', task);
		const tasksContainer = document.getElementById('activeTasks');
		let taskElement = document.getElementById(`task-${task.task_id}`);

		if (!taskElement) {
			console.log('Creating new task element');
			taskElement = document.createElement('div');
			taskElement.id = `task-${task.task_id}`;
			taskElement.className = 'task-card';
			tasksContainer.appendChild(taskElement);
		}

		// 获取进度信息
		const progress = task.progress || {};
		const lastMessage = task.last_message || '';

		// 检查是否需要用户输入
		if (task.user_input_required && task.state === 'waiting_user_input') {
			console.log('Task requires user input:', task.user_input_required);
			const inputRequest = task.user_input_required;
			if (inputRequest.type === 'continue_search') {
				console.log('Creating continue_search interaction message');
				// 创建交互消息组件
				const confirmDiv = document.createElement('div');
				confirmDiv.className = 'message ai-message';
				confirmDiv.innerHTML = `
                    <div class="message-content">
                        <div class="search-interaction">
                            <p>${inputRequest.message}</p>
                            <p>当前已获取 ${inputRequest.current_results} 条结果</p>
                            <div class="interaction-buttons">
                                <button onclick="Task.submitUserInput('${task.task_id}', true)">继续搜索</button>
                                <button onclick="Task.submitUserInput('${task.task_id}', false)">查看结果</button>
                            </div>
                        </div>
                    </div>
                `;
				const chatHistory = document.getElementById('chatHistory');
				console.log('Appending interaction message to chat history');
				chatHistory.appendChild(confirmDiv);
				Chat.scrollToBottom();
			}
		}

		// 更新任务状态显示
		taskElement.innerHTML = `
            <div class="task-info">
                <div class="task-header">
                    <strong>搜索：${task.keywords}</strong>
                    <span class="task-state">${task.state}</span>
                </div>
                
                <div class="task-progress">
                    <div class="task-progress-bar" 
                         style="width: ${progress.percentage || 0}%">
                    </div>
                </div>
                
                <div class="task-details">
                    ${progress.current_keyword ?
				`<div>当前关键词：${progress.current_keyword}</div>` :
				''
			}
                    <div class="progress-stats">
                        <span>关键词：${progress.keywords_completed || 0}/${progress.keywords_total || 0}</span>
                        <span>笔记：${progress.notes_processed || 0}/${progress.notes_total || 0}</span>
                        <span>评论：${progress.comments_processed || 0}</span>
                    </div>
                    <div class="task-message">${lastMessage}</div>
                </div>
            </div>
            <div class="task-actions">
                ${task.state === 'running' ?
				`<button class="control-button" onclick="Task.cancelAutoSearch('${task.task_id}')">取消</button>` :
				''
			}
            </div>
        `;

		// 只有在真正完成时才考虑移除
		if (task.state === 'completed' || task.state === 'failed' || task.state === 'cancelled') {
			setTimeout(() => {
				taskElement.remove();
			}, 5000);
		}
	},

	// 处理搜索结果
	handleSearchResult(content) {
		console.log('Handling search result:', content);

		// 1. 展示文字总结（Markdown格式）
		const summaryElement = document.getElementById('analysisSummary');
		if (summaryElement && content.text_summary) {
			// 使用 marked 处理 Markdown
			summaryElement.innerHTML = marked.parse(content.text_summary);
		}

		// 2. 显示基础统计信息
		if (content.basic_stats) {
			// 使用 HTML 模板创建统计信息
			const statsHtml = `
				<div class="stats-summary">
					<h4>搜索统计</h4>
					<ul>
						<li>处理关键词：${content.basic_stats.keywords_processed} 个</li>
						<li>分析笔记：${content.basic_stats.total_notes} 篇</li>
						<li>收集评论：${content.basic_stats.total_comments} 条</li>
					</ul>
				</div>
			`;
			// 使用 isHtml 参数添加消息
			Chat.addMessage('ai', statsHtml, true);
		}

		// 3. 调用 Visualization 处理可视化数据
		if (content.visualization_data) {
			Visualization.handleSearchResult(content.visualization_data);
		}
	}
}; 