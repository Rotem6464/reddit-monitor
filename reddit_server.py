#!/usr/bin/env python3
"""
Reddit Local Web Server
Serves the web interface and handles Reddit API calls without CORS issues
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import requests
import random
import time
import os
from datetime import datetime

class RedditServerHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_html()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def send_cors_headers(self):
        """Send CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def serve_html(self):
        """Serve the HTML interface"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Data Explorer - Local Server</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }

        .controls {
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }

        .control-row {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }

        .control-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 150px;
            flex: 1;
        }

        .control-group label {
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }

        .control-group input,
        .control-group select {
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
        }

        .control-group input:focus,
        .control-group select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }

        .btn-success {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn-info {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
        }

        .status {
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }

        .status.loading {
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .posts-container {
            padding: 30px;
        }

        .posts-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .posts-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
        }

        .export-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .post-card {
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }

        .post-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            border-color: #667eea;
        }

        .post-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
            gap: 15px;
        }

        .post-position {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            flex-shrink: 0;
        }

        .post-content {
            flex: 1;
        }

        .post-title {
            font-size: 1.2rem;
            font-weight: 600;
            color: #1a73e8;
            margin-bottom: 8px;
            line-height: 1.4;
        }

        .post-title a {
            color: inherit;
            text-decoration: none;
        }

        .post-title a:hover {
            text-decoration: underline;
        }

        .post-meta {
            display: flex;
            gap: 20px;
            color: #6c757d;
            font-size: 0.9rem;
            align-items: center;
            flex-wrap: wrap;
        }

        .post-meta span {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .post-stats {
            display: flex;
            gap: 15px;
            align-items: center;
        }

        .stat {
            background: #f8f9fa;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .stat.score {
            color: #ff6b6b;
        }

        .stat.comments {
            color: #667eea;
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }

        .empty-state h3 {
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }

        .reddit-url {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border: 1px solid #dee2e6;
        }

        .reddit-url strong {
            color: #495057;
        }

        .reddit-url a {
            color: #1a73e8;
            text-decoration: none;
            word-break: break-all;
        }

        .reddit-url a:hover {
            text-decoration: underline;
        }

        .server-info {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #c3e6cb;
        }

        @media (max-width: 768px) {
            .control-row {
                flex-direction: column;
                align-items: stretch;
            }

            .control-group {
                min-width: unset;
            }

            .post-header {
                flex-direction: column;
                align-items: stretch;
            }

            .post-stats {
                justify-content: space-between;
            }

            .export-buttons {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Reddit Data Explorer</h1>
            <p>Local Server Edition - No CORS Issues!</p>
        </div>

        <div class="controls">
            <div class="server-info">
                ✅ <strong>Local Server Active!</strong> This version bypasses browser restrictions and can fetch Reddit data directly.
            </div>

            <div class="control-row">
                <div class="control-group">
                    <label for="subreddit">📍 Subreddit</label>
                    <input type="text" id="subreddit" placeholder="e.g., travel, programming" value="programming">
                </div>
                
                <div class="control-group">
                    <label for="sortType">📊 Sort Type</label>
                    <select id="sortType">
                        <option value="hot">🔥 Hot</option>
                        <option value="new">🆕 New</option>
                        <option value="top">⭐ Top</option>
                        <option value="rising">📈 Rising</option>
                        <option value="controversial">⚡ Controversial</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="timeFilter">⏰ Time Filter</label>
                    <select id="timeFilter">
                        <option value="hour">Now (Last Hour)</option>
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                        <option value="all">All Time</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="limit">📊 Number of Posts</label>
                    <select id="limit">
                        <option value="10">10 posts</option>
                        <option value="25" selected>25 posts</option>
                        <option value="50">50 posts</option>
                        <option value="100">100 posts</option>
                    </select>
                </div>
            </div>

            <div class="control-row">
                <button class="btn btn-primary" onclick="fetchRedditData()">
                    🔍 Extract Posts
                </button>
                <button class="btn btn-info" onclick="openRedditUrl()">
                    🌐 Open in Reddit
                </button>
            </div>

            <div id="status"></div>
            
            <div id="redditUrl" class="reddit-url" style="display: none;">
                <strong>📍 Reddit URL:</strong> <br>
                <a id="redditLink" href="#" target="_blank"></a>
            </div>
        </div>

        <div class="posts-container">
            <div class="posts-header">
                <h2 class="posts-title" id="postsTitle">Ready to extract Reddit posts</h2>
                <div class="export-buttons" id="exportButtons" style="display: none;">
                    <button class="btn btn-success" onclick="exportToText()">
                        📄 Export Text
                    </button>
                    <button class="btn btn-success" onclick="exportToCsv()">
                        📊 Export CSV
                    </button>
                </div>
            </div>

            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Get Started</h3>
                    <p>Enter a subreddit and click "Extract Posts" to see Reddit data automatically!</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentPosts = [];
        let currentConfig = {};

        function buildRedditUrl() {
            const subreddit = document.getElementById('subreddit').value || 'programming';
            const sortType = document.getElementById('sortType').value;
            const timeFilter = document.getElementById('timeFilter').value;
            
            let url = `https://www.reddit.com/r/${subreddit}/${sortType}`;
            if (timeFilter !== 'all') {
                url += `?t=${timeFilter}`;
            }
            
            return url;
        }

        function updateRedditUrl() {
            const url = buildRedditUrl();
            document.getElementById('redditLink').href = url;
            document.getElementById('redditLink').textContent = url;
            document.getElementById('redditUrl').style.display = 'block';
        }

        function openRedditUrl() {
            const url = buildRedditUrl();
            window.open(url, '_blank');
            updateRedditUrl();
        }

        function showStatus(message, type = 'loading') {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }

        function hideStatus() {
            document.getElementById('status').style.display = 'none';
        }

        async function fetchRedditData() {
            const subreddit = document.getElementById('subreddit').value.trim();
            if (!subreddit) {
                showStatus('Please enter a subreddit name', 'error');
                return;
            }

            currentConfig = {
                subreddit: subreddit,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value,
                limit: document.getElementById('limit').value
            };

            showStatus('🔍 Fetching Reddit data via local server...', 'loading');
            updateRedditUrl();

            try {
                const apiUrl = `/api/reddit?subreddit=${encodeURIComponent(currentConfig.subreddit)}&sort=${currentConfig.sortType}&time=${currentConfig.timeFilter}&limit=${currentConfig.limit}`;
                
                console.log('Fetching from local server:', apiUrl);

                const response = await fetch(apiUrl);
                const result = await response.json();

                if (result.success) {
                    const posts = result.posts;
                    
                    if (posts.length > 0) {
                        displayPosts(posts);
                        showStatus(`✅ Successfully extracted ${posts.length} posts from r/${subreddit}`, 'success');
                        currentPosts = posts;
                        document.getElementById('exportButtons').style.display = 'flex';
                    } else {
                        showStatus('❌ No posts found. Subreddit might be private or empty.', 'error');
                        displayEmptyState();
                    }
                } else {
                    showStatus(`❌ ${result.error}`, 'error');
                    displayEmptyState();
                }

            } catch (error) {
                console.error('Error fetching Reddit data:', error);
                showStatus('❌ Failed to fetch data. Make sure the local server is running.', 'error');
                displayEmptyState();
            }
        }

        function displayPosts(posts) {
            const container = document.getElementById('postsContainer');
            const title = document.getElementById('postsTitle');
            
            title.textContent = `📊 ${posts.length} posts from r/${currentConfig.subreddit} (${currentConfig.sortType} - ${currentConfig.timeFilter})`;
            
            container.innerHTML = posts.map(post => `
                <div class="post-card">
                    <div class="post-header">
                        <div class="post-position">${post.position}</div>
                        <div class="post-content">
                            <div class="post-title">
                                <a href="${post.url}" target="_blank">${post.title}</a>
                            </div>
                            <div class="post-meta">
                                <span>👤 u/${post.author}</span>
                                <span>📅 ${post.created}</span>
                            </div>
                        </div>
                        <div class="post-stats">
                            <div class="stat score">
                                📊 ${formatNumber(post.score)}
                            </div>
                            <div class="stat comments">
                                💬 ${formatNumber(post.comments)}
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function displayEmptyState() {
            const container = document.getElementById('postsContainer');
            const title = document.getElementById('postsTitle');
            
            title.textContent = 'No posts found';
            document.getElementById('exportButtons').style.display = 'none';
            
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try a different subreddit or check if it's public</p>
                </div>
            `;
        }

        function formatNumber(num) {
            if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'k';
            }
            return num.toString();
        }

        function exportToText() {
            if (currentPosts.length === 0) return;

            const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
            const filename = `reddit_${currentConfig.subreddit}_${currentConfig.sortType}_${timestamp}.txt`;
            
            let content = `Reddit Posts Export\\n`;
            content += `${'='.repeat(50)}\\n`;
            content += `Subreddit: r/${currentConfig.subreddit}\\n`;
            content += `Sort: ${currentConfig.sortType}\\n`;
            content += `Time Filter: ${currentConfig.timeFilter}\\n`;
            content += `Total Posts: ${currentPosts.length}\\n`;
            content += `Export Date: ${new Date().toLocaleString()}\\n`;
            content += `${'='.repeat(50)}\\n\\n`;

            currentPosts.forEach(post => {
                content += `POST #${post.position}\\n`;
                content += `Title: ${post.title}\\n`;
                content += `Author: u/${post.author}\\n`;
                content += `Score: ${post.score} points\\n`;
                content += `Comments: ${post.comments}\\n`;
                content += `URL: ${post.url}\\n`;
                content += `Created: ${post.created}\\n`;
                content += `${'-'.repeat(60)}\\n\\n`;
            });

            downloadFile(content, filename, 'text/plain');
        }

        function exportToCsv() {
            if (currentPosts.length === 0) return;

            const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
            const filename = `reddit_${currentConfig.subreddit}_${currentConfig.sortType}_${timestamp}.csv`;
            
            const headers = ['Position', 'Title', 'Author', 'Score', 'Comments', 'URL', 'Created', 'Subreddit'];
            let csv = headers.join(',') + '\\n';

            currentPosts.forEach(post => {
                const row = [
                    post.position,
                    `"${post.title.replace(/"/g, '""')}"`,
                    post.author,
                    post.score,
                    post.comments,
                    post.url,
                    `"${post.created}"`,
                    post.subreddit
                ];
                csv += row.join(',') + '\\n';
            });

            downloadFile(csv, filename, 'text/csv');
        }

        function downloadFile(content, filename, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            showStatus(`💾 Downloaded: ${filename}`, 'success');
        }

        // Initialize
        updateRedditUrl();
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def handle_reddit_api(self):
        """Handle Reddit API requests"""
        try:
            # Parse query parameters
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['all'])[0]
            limit = params.get('limit', ['25'])[0]
            
            print(f"API Request: r/{subreddit}, {sort_type}, {time_filter}, limit={limit}")
            
            # Fetch Reddit data
            posts = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': 'Failed to fetch Reddit data. Subreddit may be private or not exist.',
                    'posts': []
                }
            
            # Send JSON response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            print(f"API Error: {e}")
            error_response = {
                'success': False,
                'error': f'Server error: {str(e)}',
                'posts': []
            }
            
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with proper headers and error handling"""
        try:
            # Build Reddit JSON URL
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            print(f"Fetching: {url}")
            
            # Random delay to be respectful
            time.sleep(random.uniform(1, 3))
            
            # Make request with proper headers
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                print(f"✅ Successfully fetched {len(posts)} posts")
                return posts
            elif response.status_code == 403:
                print("❌ 403 Forbidden - Private subreddit or blocked")
                return None
            else:
                print(f"❌ HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching Reddit data: {e}")
            return None
    
    def parse_reddit_json(self, data):
        """Parse Reddit JSON response"""
        posts = []
        
        try:
            # Handle Reddit JSON structure
            if isinstance(data, dict) and 'data' in data:
                children = data['data'].get('children', [])
            elif isinstance(data, list) and len(data) > 0:
                children = data[0]['data'].get('children', [])
            else:
                return posts
            
            for i, child in enumerate(children, 1):
                post_data = child.get('data', {})
                
                if post_data and post_data.get('title'):
                    post = {
                        'position': i,
                        'title': post_data.get('title', 'No title'),
                        'author': post_data.get('author', 'Unknown'),
                        'score': post_data.get('score', 0),
                        'comments': post_data.get('num_comments', 0),
                        'url': f"https://reddit.com{post_data.get('permalink', '')}",
                        'created': datetime.fromtimestamp(post_data.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M'),
                        'subreddit': post_data.get('subreddit', 'unknown')
                    }
                    posts.append(post)
            
        except Exception as e:
            print(f"❌ Error parsing JSON: {e}")
        
        return posts
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def run_server(port=8080):
    """Run the local server"""
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, RedditServerHandler)
    
    print(f"🚀 Reddit Data Explorer Server")
    print(f"=" * 40)
    print(f"🌐 Server running at: http://localhost:{port}")
    print(f"📱 Open this URL in your browser to use the interface")
    print(f"🛑 Press Ctrl+C to stop the server")
    print(f"=" * 40)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n👋 Server stopped.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
