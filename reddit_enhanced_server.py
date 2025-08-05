#!/usr/bin/env python3
"""
Enhanced Reddit Server with Google Search & Notifications
- Uses DataForSEO API for private subreddits via Google search
- Slack and email notifications for new posts
- Auto-monitoring capabilities
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import requests
import random
import time
import os
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from datetime import datetime, timedelta
import threading
import base64
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class NotificationConfig:
    slack_webhook: str = ""
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: List[str] = None
    
    def __post_init__(self):
        if self.email_recipients is None:
            self.email_recipients = []

class EnhancedRedditHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # DataForSEO API credentials (you'll need to add yours)
        self.dataforseo_login = "your_dataforseo_login"  # Replace with your login
        self.dataforseo_password = "your_dataforseo_password"  # Replace with your password
        
        # Notification config
        self.notification_config = NotificationConfig()
        
        # Monitoring state
        self.monitored_subreddits = {}
        
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_html()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path.startswith('/api/google-search'):
            self.handle_google_search_api()
        elif self.path.startswith('/api/notifications'):
            self.handle_notifications_api()
        elif self.path.startswith('/api/monitor'):
            self.handle_monitor_api()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path.startswith('/api/notifications/config'):
            self.handle_notification_config(post_data)
        elif self.path.startswith('/api/monitor/start'):
            self.handle_start_monitoring(post_data)
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
        """Serve the enhanced HTML interface"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Reddit Data Explorer</title>
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

        .features-row {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
            justify-content: center;
        }

        .feature-badge {
            background: rgba(255,255,255,0.2);
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.9rem;
            font-weight: 500;
        }

        .tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }

        .tab {
            flex: 1;
            padding: 15px 20px;
            background: transparent;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 600;
            color: #6c757d;
            transition: all 0.3s ease;
        }

        .tab.active {
            background: white;
            color: #495057;
            border-bottom: 3px solid #667eea;
        }

        .tab:hover {
            background: #e9ecef;
        }

        .tab-content {
            display: none;
            padding: 30px;
        }

        .tab-content.active {
            display: block;
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
        .control-group select,
        .control-group textarea {
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
        }

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .control-group textarea {
            resize: vertical;
            min-height: 100px;
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

        .btn-success {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn-warning {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }

        .btn-info {
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
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

        .status.warning {
            background: #fff3e0;
            color: #ef6c00;
            border: 1px solid #ffcc02;
        }

        .info-box {
            background: #e3f2fd;
            border: 1px solid #bbdefb;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }

        .info-box h4 {
            color: #1976d2;
            margin-bottom: 10px;
        }

        .info-box ul {
            color: #1976d2;
            padding-left: 20px;
        }

        .private-subreddit-notice {
            background: #fff3e0;
            border: 1px solid #ffcc02;
            border-radius: 10px;
            padding: 15px;
            margin: 20px 0;
        }

        .private-subreddit-notice h4 {
            color: #ef6c00;
            margin-bottom: 10px;
        }

        .monitoring-card {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
        }

        .monitoring-card h4 {
            color: #495057;
            margin-bottom: 10px;
        }

        .monitoring-status {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
        }

        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }

        .status-indicator.active {
            background: #28a745;
        }

        .status-indicator.inactive {
            background: #6c757d;
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

        .search-source {
            background: #e3f2fd;
            color: #1976d2;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-left: 10px;
        }

        @media (max-width: 768px) {
            .control-row {
                flex-direction: column;
                align-items: stretch;
            }

            .control-group {
                min-width: unset;
            }

            .tabs {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Enhanced Reddit Data Explorer</h1>
            <p>Advanced Reddit monitoring with Google search fallback & notifications</p>
            <div class="features-row">
                <div class="feature-badge">🔍 Google Search Fallback</div>
                <div class="feature-badge">📱 Slack Notifications</div>
                <div class="feature-badge">📧 Email Alerts</div>
                <div class="feature-badge">⏰ Auto Monitoring</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" onclick="showTab('extract')">🔍 Extract Posts</button>
            <button class="tab" onclick="showTab('notifications')">📱 Notifications</button>
            <button class="tab" onclick="showTab('monitor')">⏰ Monitor</button>
        </div>

        <!-- Extract Posts Tab -->
        <div id="extractTab" class="tab-content active">
            <div class="info-box">
                <h4>🔧 How it works:</h4>
                <ul>
                    <li><strong>Public subreddits:</strong> Direct Reddit API access</li>
                    <li><strong>Private subreddits:</strong> Google search with site:reddit.com/r/subreddit</li>
                    <li><strong>DataForSEO API:</strong> Professional Google search results</li>
                </ul>
            </div>

            <div class="control-row">
                <div class="control-group">
                    <label for="subreddit">📍 Subreddit</label>
                    <input type="text" id="subreddit" placeholder="e.g., locallama, travel" value="programming">
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
                <button class="btn btn-warning" onclick="fetchWithGoogleSearch()">
                    🔍 Force Google Search
                </button>
                <button class="btn btn-info" onclick="openRedditUrl()">
                    🌐 Open in Reddit
                </button>
            </div>

            <div id="status"></div>
            
            <div id="postsContainer">
                <div style="text-align: center; padding: 60px 20px; color: #6c757d;">
                    <h3>🎯 Ready to Extract</h3>
                    <p>Choose a subreddit and extraction method above</p>
                </div>
            </div>
        </div>

        <!-- Notifications Tab -->
        <div id="notificationsTab" class="tab-content">
            <div class="info-box">
                <h4>📱 Set up notifications to get alerts when new posts are found:</h4>
                <ul>
                    <li><strong>Slack:</strong> Create a webhook URL in your Slack workspace</li>
                    <li><strong>Email:</strong> Use Gmail SMTP or your email provider</li>
                    <li><strong>Monitoring:</strong> Automatic checks every few minutes</li>
                </ul>
            </div>

            <h3>📱 Slack Notifications</h3>
            <div class="control-row">
                <div class="control-group">
                    <label for="slackWebhook">Slack Webhook URL</label>
                    <input type="url" id="slackWebhook" placeholder="https://hooks.slack.com/services/...">
                </div>
            </div>

            <h3>📧 Email Notifications</h3>
            <div class="control-row">
                <div class="control-group">
                    <label for="emailUsername">Email Username</label>
                    <input type="email" id="emailUsername" placeholder="your-email@gmail.com">
                </div>
                <div class="control-group">
                    <label for="emailPassword">App Password</label>
                    <input type="password" id="emailPassword" placeholder="Gmail app password">
                </div>
            </div>
            
            <div class="control-row">
                <div class="control-group">
                    <label for="emailRecipients">Recipients (comma-separated)</label>
                    <textarea id="emailRecipients" placeholder="user1@example.com, user2@example.com"></textarea>
                </div>
            </div>

            <div class="control-row">
                <button class="btn btn-success" onclick="saveNotificationConfig()">
                    💾 Save Configuration
                </button>
                <button class="btn btn-info" onclick="testNotifications()">
                    🧪 Test Notifications
                </button>
            </div>

            <div id="notificationStatus"></div>
        </div>

        <!-- Monitor Tab -->
        <div id="monitorTab" class="tab-content">
            <div class="info-box">
                <h4>⏰ Auto-monitoring checks subreddits periodically and sends notifications for new posts:</h4>
                <ul>
                    <li><strong>Frequency:</strong> Check every 5-30 minutes</li>
                    <li><strong>Smart detection:</strong> Only notify for truly new posts</li>
                    <li><strong>Multiple subreddits:</strong> Monitor several at once</li>
                </ul>
            </div>

            <h3>📍 Add Subreddit to Monitor</h3>
            <div class="control-row">
                <div class="control-group">
                    <label for="monitorSubreddit">Subreddit</label>
                    <input type="text" id="monitorSubreddit" placeholder="e.g., locallama">
                </div>
                <div class="control-group">
                    <label for="monitorInterval">Check Interval (minutes)</label>
                    <select id="monitorInterval">
                        <option value="5">Every 5 minutes</option>
                        <option value="10" selected>Every 10 minutes</option>
                        <option value="15">Every 15 minutes</option>
                        <option value="30">Every 30 minutes</option>
                        <option value="60">Every hour</option>
                    </select>
                </div>
            </div>

            <div class="control-row">
                <button class="btn btn-success" onclick="startMonitoring()">
                    ▶️ Start Monitoring
                </button>
                <button class="btn btn-warning" onclick="stopMonitoring()">
                    ⏸️ Stop All Monitoring
                </button>
            </div>

            <div id="monitorStatus"></div>

            <h3>📊 Active Monitors</h3>
            <div id="activeMonitors">
                <div style="text-align: center; padding: 40px; color: #6c757d;">
                    <p>No active monitors yet</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentPosts = [];
        let currentConfig = {};

        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });

            // Show selected tab
            document.getElementById(tabName + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }

        function showStatus(message, type = 'loading', containerId = 'status') {
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }

        function openRedditUrl() {
            const subreddit = document.getElementById('subreddit').value || 'programming';
            const sortType = document.getElementById('sortType').value;
            const timeFilter = document.getElementById('timeFilter').value;
            
            let url = `https://www.reddit.com/r/${subreddit}/${sortType}`;
            if (timeFilter !== 'all') {
                url += `?t=${timeFilter}`;
            }
            
            window.open(url, '_blank');
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

            showStatus('🔍 Fetching Reddit data...', 'loading');

            try {
                const apiUrl = `/api/reddit?subreddit=${encodeURIComponent(currentConfig.subreddit)}&sort=${currentConfig.sortType}&time=${currentConfig.timeFilter}&limit=${currentConfig.limit}`;
                
                const response = await fetch(apiUrl);
                const result = await response.json();

                if (result.success) {
                    displayPosts(result.posts, 'Reddit API');
                    showStatus(`✅ Successfully extracted ${result.posts.length} posts from r/${subreddit}`, 'success');
                    currentPosts = result.posts;
                } else {
                    showStatus(`❌ Reddit API failed: ${result.error}`, 'warning');
                    showPrivateSubredditNotice();
                }

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Failed to fetch from Reddit API', 'error');
            }
        }

        async function fetchWithGoogleSearch() {
            const subreddit = document.getElementById('subreddit').value.trim();
            if (!subreddit) {
                showStatus('Please enter a subreddit name', 'error');
                return;
            }

            showStatus('🔍 Searching Google for Reddit posts...', 'loading');

            try {
                const apiUrl = `/api/google-search?subreddit=${encodeURIComponent(subreddit)}&limit=${document.getElementById('limit').value}`;
                
                const response = await fetch(apiUrl);
                const result = await response.json();

                if (result.success) {
                    displayPosts(result.posts, 'Google Search');
                    showStatus(`✅ Found ${result.posts.length} posts via Google search`, 'success');
                    currentPosts = result.posts;
                } else {
                    showStatus(`❌ Google search failed: ${result.error}`, 'error');
                }

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Failed to search Google', 'error');
            }
        }

        function showPrivateSubredditNotice() {
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="private-subreddit-notice">
                    <h4>🔒 Private Subreddit Detected</h4>
                    <p>This subreddit appears to be private. Try the <strong>"Force Google Search"</strong> button to find posts via Google indexing.</p>
                    <button class="btn btn-warning" onclick="fetchWithGoogleSearch()" style="margin-top: 10px;">
                        🔍 Search with Google
                    </button>
                </div>
            `;
        }

        function displayPosts(posts, source) {
            const container = document.getElementById('postsContainer');
            
            if (posts.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 60px 20px; color: #6c757d;">
                        <h3>🔍 No Posts Found</h3>
                        <p>Try a different subreddit or search method</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = `
                <h3>📊 ${posts.length} posts from r/${currentConfig.subreddit} 
                    <span class="search-source">${source}</span>
                </h3>
                <div style="margin-bottom: 20px;">
                    <button class="btn btn-success" onclick="exportToText()">📄 Export Text</button>
                    <button class="btn btn-success" onclick="exportToCsv()">📊 Export CSV</button>
                </div>
            ` + posts.map(post => `
                <div class="post-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 15px;">
                        <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0;">
                            ${post.position}
                        </div>
                        <div style="flex: 1;">
                            <div style="font-size: 1.2rem; font-weight: 600; color: #1a73e8; margin-bottom: 8px; line-height: 1.4;">
                                <a href="${post.url}" target="_blank" style="color: inherit; text-decoration: none;">${post.title}</a>
                            </div>
                            <div style="display: flex; gap: 20px; color: #6c757d; font-size: 0.9rem; align-items: center; flex-wrap: wrap;">
                                <span>👤 u/${post.author}</span>
                                <span>📅 ${post.created || 'Recent'}</span>
                            </div>
                        </div>
                        <div style="display: flex; gap: 15px; align-items: center;">
                            <div style="background: #f8f9fa; padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; color: #ff6b6b;">
                                📊 ${formatNumber(post.score || 0)}
                            </div>
                            <div style="background: #f8f9fa; padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; color: #667eea;">
                                💬 ${formatNumber(post.comments || 0)}
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function formatNumber(num) {
            if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'k';
            }
            return num.toString();
        }

        async function saveNotificationConfig() {
            const config = {
                slack_webhook: document.getElementById('slackWebhook').value,
                email_username: document.getElementById('emailUsername').value,
                email_password: document.getElementById('emailPassword').value,
                email_recipients: document.getElementById('emailRecipients').value.split(',').map(s => s.trim()).filter(s => s)
            };

            try {
                const response = await fetch('/api/notifications/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });

                const result = await response.json();
                
                if (result.success) {
                    showStatus('✅ Notification configuration saved!', 'success', 'notificationStatus');
                } else {
                    showStatus(`❌ Failed to save: ${result.error}`, 'error', 'notification

