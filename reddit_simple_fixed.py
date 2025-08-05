#!/usr/bin/env python3
"""
Complete Simple Reddit Monitor - Python 3.13 Compatible
Shows 3-5 top posts and sends weekly/monthly email alerts
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import requests
import random
import time
import smtplib
from datetime import datetime, timedelta
import threading
import schedule
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class SimpleRedditHandler(BaseHTTPRequestHandler):
    # Class variable to store subscriptions across all instances
    email_subscriptions = []
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        ]
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_html()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/subscriptions':
            self.handle_get_subscriptions()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path.startswith('/api/subscribe'):
            self.handle_email_subscription(post_data)
        elif self.path.startswith('/api/unsubscribe'):
            self.handle_unsubscribe(post_data)
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        """Handle OPTIONS for CORS"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def send_cors_headers(self):
        """Send CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def serve_html(self):
        """Serve the simple HTML interface"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple Reddit Monitor</title>
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
            max-width: 800px;
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
            font-size: 2.2rem;
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
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }

        .control-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 150px;
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
            align-self: end;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-success {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
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

        .posts-container {
            padding: 30px;
        }

        .posts-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }

        .post-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }

        .post-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }

        .post-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }

        .post-number {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            width: 45px;
            height: 45px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 1.2rem;
            flex-shrink: 0;
        }

        .post-title {
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
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
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .post-author {
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }

        .post-stats {
            display: flex;
            gap: 20px;
        }

        .stat {
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .stat.score {
            color: #ff6b6b;
        }

        .stat.comments {
            color: #667eea;
        }

        .email-section {
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }

        .email-section h3 {
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }

        .email-form {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: end;
        }

        .email-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
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

        .subscriptions-section {
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
            margin-top: 20px;
        }

        .subscription-item {
            background: white;
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .btn-danger {
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }

        @media (max-width: 768px) {
            .control-row,
            .email-form {
                flex-direction: column;
                align-items: stretch;
            }

            .btn {
                align-self: stretch;
            }

            .post-meta {
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }

            .post-stats {
                justify-content: center;
            }

            .subscription-item {
                flex-direction: column;
                gap: 10px;
                align-items: stretch;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Simple Reddit Monitor</h1>
            <p>Get the top 5 posts from any subreddit + email alerts</p>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddit">📍 Subreddit</label>
                    <input type="text" id="subreddit" placeholder="e.g., travel, programming" value="programming">
                </div>
                
                <div class="control-group">
                    <label for="sortType">📊 Sort By</label>
                    <select id="sortType">
                        <option value="hot">🔥 Hot</option>
                        <option value="top">⭐ Top</option>
                        <option value="new">🆕 New</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="timeFilter">⏰ Time Period</label>
                    <select id="timeFilter">
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                        <option value="all">All Time</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Get Top 5 Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Choose a subreddit and click "Get Top 5 Posts" to see the best content!</p>
                </div>
            </div>
        </div>

        <div class="email-section" id="emailSection" style="display: none;">
            <h3>📧 Get Email Alerts for These Posts</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get similar top posts delivered to your email weekly or monthly
            </p>
            
            <div class="email-form">
                <div class="email-group">
                    <label for="userEmail">Your Email Address</label>
                    <input type="email" id="userEmail" placeholder="your-email@example.com">
                </div>
                
                <div class="email-group">
                    <label for="alertFrequency">Alert Frequency</label>
                    <select id="alertFrequency">
                        <option value="weekly">📅 Weekly (every Monday)</option>
                        <option value="monthly">📆 Monthly (1st of month)</option>
                    </select>
                </div>
                
                <button class="btn btn-success" onclick="subscribeToAlerts()">
                    📧 Subscribe to Alerts
                </button>
            </div>

            <div id="emailStatus"></div>
        </div>

        <div class="subscriptions-section" id="subscriptionsSection" style="display: none;">
            <h3>📋 Your Active Subscriptions</h3>
            <button class="btn btn-primary" onclick="loadSubscriptions()" style="margin-bottom: 15px;">
                🔄 Refresh Subscriptions
            </button>
            <div id="subscriptionsList"></div>
        </div>
    </div>

    <script>
        let currentPosts = [];
        let currentConfig = {};

        function showStatus(message, type = 'loading', containerId = 'status') {
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }

        function hideStatus(containerId = 'status') {
            document.getElementById(containerId).style.display = 'none';
        }

        async function fetchPosts() {
            const subreddit = document.getElementById('subreddit').value.trim();
            if (!subreddit) {
                showStatus('Please enter a subreddit name', 'error');
                return;
            }

            currentConfig = {
                subreddit: subreddit,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            };

            showStatus('🔍 Fetching top 5 posts...', 'loading');

            try {
                const apiUrl = `/api/reddit?subreddit=${encodeURIComponent(currentConfig.subreddit)}&sort=${currentConfig.sortType}&time=${currentConfig.timeFilter}&limit=5`;
                
                const response = await fetch(apiUrl);
                const result = await response.json();

                if (result.success && result.posts.length > 0) {
                    displayPosts(result.posts);
                    showStatus(`✅ Found ${result.posts.length} top posts from r/${subreddit}!`, 'success');
                    document.getElementById('emailSection').style.display = 'block';
                    document.getElementById('subscriptionsSection').style.display = 'block';
                    currentPosts = result.posts;
                    loadSubscriptions();
                } else {
                    showStatus('❌ No posts found. Try a different subreddit or check if it exists.', 'error');
                    document.getElementById('emailSection').style.display = 'none';
                    displayEmptyState();
                }

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
                document.getElementById('emailSection').style.display = 'none';
            }
        }

        function displayPosts(posts) {
            const container = document.getElementById('postsContainer');
            
            container.innerHTML = `
                <h2 class="posts-title">🏆 Top ${posts.length} Posts from r/${currentConfig.subreddit}</h2>
            ` + posts.map(post => `
                <div class="post-card">
                    <div class="post-header">
                        <div class="post-number">${post.position}</div>
                        <div class="post-title">
                            <a href="${post.url}" target="_blank">${post.title}</a>
                        </div>
                    </div>
                    <div class="post-meta">
                        <div class="post-author">👤 by u/${post.author}</div>
                        <div class="post-stats">
                            <div class="stat score">
                                👍 ${formatNumber(post.score)}
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
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try a different subreddit or check the spelling</p>
                </div>
            `;
        }

        function formatNumber(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return num.toString();
        }

        async function subscribeToAlerts() {
            const email = document.getElementById('userEmail').value.trim();
            const frequency = document.getElementById('alertFrequency').value;

            if (!email) {
                showStatus('Please enter your email address', 'error', 'emailStatus');
                return;
            }

            if (!email.includes('@')) {
                showStatus('Please enter a valid email address', 'error', 'emailStatus');
                return;
            }

            showStatus('📧 Setting up your email alerts...', 'loading', 'emailStatus');

            try {
                const subscriptionData = {
                    email: email,
                    frequency: frequency,
                    subreddit: currentConfig.subreddit,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                };

                const response = await fetch('/api/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(subscriptionData)
                });

                const result = await response.json();

                if (result.success) {
                    showStatus(`✅ Success! You'll receive ${frequency} alerts for r/${currentConfig.subreddit} at ${email}`, 'success', 'emailStatus');
                    loadSubscriptions();
                } else {
                    showStatus(`❌ Subscription failed: ${result.error}`, 'error', 'emailStatus');
                }

            } catch (error) {
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up alerts. Please try again.', 'error', 'emailStatus');
            }
        }

        async function loadSubscriptions() {
            try {
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success) {
                    displaySubscriptions(result.subscriptions);
                }
            } catch (error) {
                console.error('Failed to load subscriptions:', error);
            }
        }

        function displaySubscriptions(subscriptions) {
            const container = document.getElementById('subscriptionsList');
            
            if (subscriptions.length === 0) {
                container.innerHTML = '<p style="color: #6c757d;">No active subscriptions</p>';
                return;
            }

            container.innerHTML = subscriptions.map(sub => `
                <div class="subscription-item">
                    <div>
                        <strong>r/${sub.subreddit}</strong> - ${sub.frequency} alerts to ${sub.email}
                        <br><small>Next email: ${new Date(sub.next_send).toLocaleDateString()}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribe('${sub.email}', '${sub.subreddit}')">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `).join('');
        }

        async function unsubscribe(email, subreddit) {
            if (!confirm(`Are you sure you want to unsubscribe from r/${subreddit}?`)) {
                return;
            }

            try {
                const response = await fetch('/api/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, subreddit })
                });

                const result = await response.json();
                
                if (result.success) {
                    loadSubscriptions();
                    showStatus('✅ Successfully unsubscribed', 'success', 'emailStatus');
                } else {
                    showStatus('❌ Failed to unsubscribe', 'error', 'emailStatus');
                }
            } catch (error) {
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'emailStatus');
            }
        }

        // Auto-focus on subreddit input
        document.getElementById('subreddit').focus();
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def handle_reddit_api(self):
        """Handle Reddit API requests - limit to 5 posts"""
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['week'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)  # Max 5 posts
            
            print(f"📊 Fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
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
            
            self.send_json_response(response_data)
            
        except Exception as e:
            print(f"❌ Reddit API Error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Server error: {str(e)}',
                'posts': []
            }, 500)
    
    def handle_get_subscriptions(self):
        """Handle getting all subscriptions"""
        try:
            self.send_json_response({
                'success': True,
                'subscriptions': SimpleRedditHandler.email_subscriptions,
                'total': len(SimpleRedditHandler.email_subscriptions)
            })
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        try:
            data = json.loads(post_data.decode())
            email = data.get('email', '').strip()
            subreddit = data.get('subreddit', '').strip()
            
            if not email or not subreddit:
                self.send_json_response({
                    'success': False,
                    'error': 'Email and subreddit are required'
                })
                return
            
            # Remove subscription
            original_count = len(SimpleRedditHandler.email_subscriptions)
            SimpleRedditHandler.email_subscriptions = [
                sub for sub in SimpleRedditHandler.email_subscriptions 
                if not (sub['email'] == email and sub['subreddit'] == subreddit)
            ]
            
            removed_count = original_count - len(SimpleRedditHandler.email_subscriptions)
            
            if removed_count > 0:
                print(f"📧 Removed subscription: {email} from r/{subreddit}")
                self.send_json_response({
                    'success': True,
                    'message': f'Successfully unsubscribed from r/{subreddit}'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Subscription not found'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_email_subscription(self, post_data):
        """Handle email subscription requests"""
        try:
            subscription_data = json.loads(post_data.decode())
            
            email = subscription_data.get('email', '').strip()
            frequency = subscription_data.get('frequency', 'weekly')
            subreddit = subscription_data.get('subreddit', '')
            sort_type = subscription_data.get('sortType', 'hot')
            time_filter = subscription_data.get('timeFilter', 'week')
            posts = subscription_data.get('posts', [])
            
            if not email or '@' not in email:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid email address'
                })
                return
            
            # Store subscription
            subscription = {
                'email': email,
                'frequency': frequency,
                'subreddit': subreddit,
                'sort_type': sort_type,
                'time_filter': time_filter,
                'subscribed_at': datetime.now().isoformat(),
                'next_send': self.calculate_next_send_date(frequency)
            }
            
            # Remove existing subscription for this email/subreddit combo
            SimpleRedditHandler.email_subscriptions = [
                sub for sub in SimpleRedditHandler.email_subscriptions 
                if not (sub['email'] == email and sub['subreddit'] == subreddit)
            ]
            
            # Add new subscription
            SimpleRedditHandler.email_subscriptions.append(subscription)
            
            # Send immediate confirmation with current posts
            self.send_confirmation_email(subscription, posts)
            
            print(f"📧 New subscription: {email} for r/{subreddit} ({frequency})")
            print(f"📋 Total subscriptions: {len(SimpleRedditHandler.email_subscriptions)}")
            
            self.send_json_response({
                'success': True,
                'message': f'Subscription created! You will receive {frequency} emails for r/{subreddit}',
                'next_email': subscription['next_send']
            })
            
        except Exception as e:
            print(f"❌ Subscription Error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def calculate_next_send_date(self, frequency):
        """Calculate next email send date"""
        now = datetime.now()
        
        if frequency == 'weekly':
            # Next Monday
            days_ahead = 0 - now.weekday()  # Monday is 0
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            next_date = now + timedelta(days=days_ahead)
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        
        elif frequency == 'monthly':
            # First day of next month
            if now.month == 12:
                next_date = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_date = now.replace(month=now.month + 1, day=1)
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        
        return (now + timedelta(days=7)).isoformat()  # Default to weekly
    
    def send_confirmation_email(self, subscription, posts):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 CONFIRMATION EMAIL (SIMULATED)")
                print(f"=" * 50)
                print(f"To: {subscription['email']}")
                print(f"Subject: 🎉 Subscription Confirmed: r/{subscription['subreddit']}")
                print(f"Frequency: {subscription['frequency'].title()}")
                print(f"Next email: {subscription['next_send'][:10]}")
                print(f"Posts included:")
                
                for i, post in enumerate(posts[:5], 1):
                    print(f"  {i}. {post['title'][:60]}...")
                    print(f"     👤 u/{post['author']} | 👍 {post['score']} | 💬 {post['comments']}")
                
                print(f"=" * 50)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🎉 Subscription Confirmed: r/{subscription['subreddit']}"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML email content
            html_content = self.create_email_html(subscription, posts)
            
            # Create text version
            text_content = self.create_email_text(subscription, posts)
            
            # Attach both versions
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
            
            print(f"📧 Confirmation email sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            # Fall back to logging
            print(f"📧 CONFIRMATION EMAIL (FALLBACK LOG)")
            print(f"To: {subscription['email']}")
            print(f"Subject: Subscription Confirmed for r/{subscription['subreddit']}")
            return False
    
    def create_email_html(self, subscription, posts):
        """Create HTML email content"""
        posts_html = ""
        for i, post in enumerate(posts[:5], 1):
            posts_html += f"""
            <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                <h3 style="margin: 0 0 10px 0; color: #1a73e8;">
                    {i}. <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                </h3>
                <p style="margin: 5px 0; color: #6c757d;">
                    👤 by u/{post['author']} | 👍 {post['score']} | 💬 {post['comments']}
                </p>
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Monitor Subscription</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Monitor</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Subscription Confirmed!</p>
                </div>
                
                <div style="padding: 30px;">
                    <h2 style="color: #495057; margin-bottom: 20px;">✅ You're all set!</h2>
                    <p style="color: #6c757d; line-height: 1.6;">
                        You've successfully subscribed to <strong>{subscription['frequency']}</strong> updates 
                        for <strong>r/{subscription['subreddit']}</strong>.
                    </p>
                    <p style="color: #6c757d; line-height: 1.6;">
                        Your next email will arrive on <strong>{subscription['next_send'][:10]}</strong>.
                    </p>
                    
                    <h3 style="color: #495057; margin: 30px 0 20px 0;">🏆 Here are today's top posts:</h3>
                    {posts_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px;">
                        <p style="margin: 0; color: #1976d2; text-align: center;">
                            📧 To unsubscribe, visit the Reddit Monitor website and use the unsubscribe feature.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_email_text(self, subscription, posts):
        """Create plain text email content"""
        posts_text = ""
        for i, post in enumerate(posts[:5], 1):
            posts_text += f"\n{i}. {post['title']}\n"
            posts_text += f"   by u/{post['author']} | Score: {post['score']} | Comments: {post['comments']}\n"
            posts_text += f"   Link: {post['url']}\n"
        
        return f"""
Reddit Monitor - Subscription Confirmed!

You've successfully subscribed to {subscription['frequency']} updates for r/{subscription['subreddit']}.

Your next email will arrive on {subscription['next_send'][:10]}.

Here are today's top posts:
{posts_text}

To unsubscribe, visit the Reddit Monitor website and use the unsubscribe feature.
        """
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with rate limiting"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            # Respectful delay
            time.sleep(random.uniform(1, 2))
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.parse_reddit_json(data)
            else:
                print(f"❌ Reddit API returned {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Reddit fetch error: {e}")
            return None
    
    def parse_reddit_json(self, data):
        """Parse Reddit JSON response"""
        posts = []
        
        try:
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
            print(f"❌ Parse error: {e}")
        
        return posts
    
    def send_json_response(self, data, status_code=200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def send_scheduled_emails():
    """Send scheduled emails to subscribers"""
    now = datetime.now()
    print(f"📅 Checking scheduled emails at {now.strftime('%Y-%m-%d %H:%M')}")
    
    if not SimpleRedditHandler.email_subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in SimpleRedditHandler.email_subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'])
            
            if now >= next_send:
                print(f"📧 Sending {subscription['frequency']} email to {subscription['email']} for r/{subscription['subreddit']}")
                
                # Create a temporary handler instance for email functionality
                handler = SimpleRedditHandler.__new__(SimpleRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                posts = handler.fetch_reddit_data(
                    subscription['subreddit'],
                    subscription['sort_type'],
                    subscription['time_filter'],
                    5
                )
                
                if posts:
                    handler.send_confirmation_email(subscription, posts)
                    emails_sent += 1
                    
                    # Update next send date
                    subscription['next_send'] = handler.calculate_next_send_date(subscription['frequency'])
                    print(f"📅 Next email scheduled for: {subscription['next_send'][:10]}")
                else:
                    print(f"❌ No posts found for r/{subscription['subreddit']}, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending scheduled email: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} scheduled emails")

def schedule_email_checker():
    """Schedule the email checking function"""
    # Check for emails every hour
    schedule.every().hour.do(send_scheduled_emails)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_email_checker, daemon=True)
    scheduler_thread.start()
    print("📅 Email scheduler started (checking every hour)")

def main():
    """Main function to start the server"""
    # Configuration
    HOST = '0.0.0.0'
    PORT = int(os.getenv('PORT', 8080))
    
    print("🚀 Starting Simple Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    print("=" * 50)
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("📧 SMTP configured - emails will be sent")
    else:
        print("📧 SMTP not configured - emails will be logged only")
        print("   Set SMTP_USERNAME and SMTP_PASSWORD environment variables to enable email sending")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), SimpleRedditHandler)
        print(f"✅ Server started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to use the Reddit Monitor")
        print("📊 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        server.server_close()
        
    except Exception as e:
        print(f"❌ Server error: {e}")

if __name__ == "__main__":
    main()#!/usr/bin/env python3
"""
Fixed Simple Reddit Monitor - Python 3.13 Compatible
Shows 3-5 top posts and sends weekly/monthly email alerts
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import requests
import random
import time
import smtplib
from datetime import datetime, timedelta
import threading
import schedule
import os

class SimpleRedditHandler(BaseHTTPRequestHandler):
    # Class variable to store subscriptions across all instances
    email_subscriptions = []
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
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
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path.startswith('/api/subscribe'):
            self.handle_email_subscription(post_data)
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        """Handle OPTIONS for CORS"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def send_cors_headers(self):
        """Send CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
    
    def serve_html(self):
        """Serve the simple HTML interface"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simple Reddit Monitor</title>
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
            max-width: 800px;
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
            font-size: 2.2rem;
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
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }

        .control-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 150px;
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
            align-self: end;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-success {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
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

        .posts-container {
            padding: 30px;
        }

        .posts-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }

        .post-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }

        .post-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }

        .post-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }

        .post-number {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            width: 45px;
            height: 45px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 1.2rem;
            flex-shrink: 0;
        }

        .post-title {
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
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
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .post-author {
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }

        .post-stats {
            display: flex;
            gap: 20px;
        }

        .stat {
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .stat.score {
            color: #ff6b6b;
        }

        .stat.comments {
            color: #667eea;
        }

        .email-section {
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }

        .email-section h3 {
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }

        .email-form {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: end;
        }

        .email-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
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

        @media (max-width: 768px) {
            .control-row,
            .email-form {
                flex-direction: column;
                align-items: stretch;
            }

            .btn {
                align-self: stretch;
            }

            .post-meta {
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }

            .post-stats {
                justify-content: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Simple Reddit Monitor</h1>
            <p>Get the top 5 posts from any subreddit + email alerts</p>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddit">📍 Subreddit</label>
                    <input type="text" id="subreddit" placeholder="e.g., travel, programming" value="programming">
                </div>
                
                <div class="control-group">
                    <label for="sortType">📊 Sort By</label>
                    <select id="sortType">
                        <option value="hot">🔥 Hot</option>
                        <option value="top">⭐ Top</option>
                        <option value="new">🆕 New</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="timeFilter">⏰ Time Period</label>
                    <select id="timeFilter">
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                        <option value="all">All Time</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Get Top 5 Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Choose a subreddit and click "Get Top 5 Posts" to see the best content!</p>
                </div>
            </div>
        </div>

        <div class="email-section" id="emailSection" style="display: none;">
            <h3>📧 Get Email Alerts for These Posts</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get similar top posts delivered to your email weekly or monthly
            </p>
            
            <div class="email-form">
                <div class="email-group">
                    <label for="userEmail">Your Email Address</label>
                    <input type="email" id="userEmail" placeholder="your-email@example.com">
                </div>
                
                <div class="email-group">
                    <label for="alertFrequency">Alert Frequency</label>
                    <select id="alertFrequency">
                        <option value="weekly">📅 Weekly (every Monday)</option>
                        <option value="monthly">📆 Monthly (1st of month)</option>
                    </select>
                </div>
                
                <button class="btn btn-success" onclick="subscribeToAlerts()">
                    📧 Subscribe to Alerts
                </button>
            </div>

            <div id="emailStatus"></div>
        </div>
    </div>

    <script>
        let currentPosts = [];
        let currentConfig = {};

        function showStatus(message, type = 'loading', containerId = 'status') {
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }

        function hideStatus(containerId = 'status') {
            document.getElementById(containerId).style.display = 'none';
        }

        async function fetchPosts() {
            const subreddit = document.getElementById('subreddit').value.trim();
            if (!subreddit) {
                showStatus('Please enter a subreddit name', 'error');
                return;
            }

            currentConfig = {
                subreddit: subreddit,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            };

            showStatus('🔍 Fetching top 5 posts...', 'loading');

            try {
                const apiUrl = `/api/reddit?subreddit=${encodeURIComponent(currentConfig.subreddit)}&sort=${currentConfig.sortType}&time=${currentConfig.timeFilter}&limit=5`;
                
                const response = await fetch(apiUrl);
                const result = await response.json();

                if (result.success && result.posts.length > 0) {
                    displayPosts(result.posts);
                    showStatus(`✅ Found ${result.posts.length} top posts from r/${subreddit}!`, 'success');
                    document.getElementById('emailSection').style.display = 'block';
                    currentPosts = result.posts;
                } else {
                    showStatus('❌ No posts found. Try a different subreddit or check if it exists.', 'error');
                    document.getElementById('emailSection').style.display = 'none';
                    displayEmptyState();
                }

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
                document.getElementById('emailSection').style.display = 'none';
            }
        }

        function displayPosts(posts) {
            const container = document.getElementById('postsContainer');
            
            container.innerHTML = `
                <h2 class="posts-title">🏆 Top ${posts.length} Posts from r/${currentConfig.subreddit}</h2>
            ` + posts.map(post => `
                <div class="post-card">
                    <div class="post-header">
                        <div class="post-number">${post.position}</div>
                        <div class="post-title">
                            <a href="${post.url}" target="_blank">${post.title}</a>
                        </div>
                    </div>
                    <div class="post-meta">
                        <div class="post-author">👤 by u/${post.author}</div>
                        <div class="post-stats">
                            <div class="stat score">
                                👍 ${formatNumber(post.score)}
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
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try a different subreddit or check the spelling</p>
                </div>
            `;
        }

        function formatNumber(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(1) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(1) + 'K';
            }
            return num.toString();
        }

        async function subscribeToAlerts() {
            const email = document.getElementById('userEmail').value.trim();
            const frequency = document.getElementById('alertFrequency').value;

            if (!email) {
                showStatus('Please enter your email address', 'error', 'emailStatus');
                return;
            }

            if (!email.includes('@')) {
                showStatus('Please enter a valid email address', 'error', 'emailStatus');
                return;
            }

            showStatus('📧 Setting up your email alerts...', 'loading', 'emailStatus');

            try {
                const subscriptionData = {
                    email: email,
                    frequency: frequency,
                    subreddit: currentConfig.subreddit,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                };

                const response = await fetch('/api/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(subscriptionData)
                });

                const result = await response.json();

                if (result.success) {
                    showStatus(`✅ Success! You'll receive ${frequency} alerts for r/${currentConfig.subreddit} at ${email}`, 'success', 'emailStatus');
                } else {
                    showStatus(`❌ Subscription failed: ${result.error}`, 'error', 'emailStatus');
                }

            } catch (error) {
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up alerts. Please try again.', 'error', 'emailStatus');
            }
        }

        // Auto-focus on subreddit input
        document.getElementById('subreddit').focus();
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def handle_reddit_api(self):
        """Handle Reddit API requests - limit to 5 posts"""
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['week'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)  # Max 5 posts
            
            print(f"📊 Fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
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
            
            self.send_json_response(response_data)
            
        except Exception as e:
            print(f"❌ Reddit API Error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Server error: {str(e)}',
                'posts': []
            }, 500)
    
    def handle_email_subscription(self, post_data):
        """Handle email subscription requests"""
        try:
            subscription_data = json.loads(post_data.decode())
            
            email = subscription_data.get('email', '').strip()
            frequency = subscription_data.get('frequency', 'weekly')
            subreddit = subscription_data.get('subreddit', '')
            sort_type = subscription_data.get('sortType', 'hot')
            time_filter = subscription_data.get('timeFilter', 'week')
            posts = subscription_data.get('posts', [])
            
            if not email or '@' not in email:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid email address'
                })
                return
            
            # Store subscription
            subscription = {
                'email': email,
                'frequency': frequency,
                'subreddit': subreddit,
                'sort_type': sort_type,
                'time_filter': time_filter,
                'subscribed_at': datetime.now().isoformat(),
                'next_send': self.calculate_next_send_date(frequency)
            }
            
            # Remove existing subscription for this email/subreddit combo
            SimpleRedditHandler.email_subscriptions = [
                sub for sub in SimpleRedditHandler.email_subscriptions 
                if not (sub['email'] == email and sub['subreddit'] == subreddit)
            ]
            
            # Add new subscription
            SimpleRedditHandler.email_subscriptions.append(subscription)
            
            # Send immediate confirmation with current posts
            self.send_confirmation_email(subscription, posts)
            
            print(f"📧 New subscription: {email} for r/{subreddit} ({frequency})")
            print(f"📋 Total subscriptions: {len(SimpleRedditHandler.email_subscriptions)}")
            
            self.send_json_response({
                'success': True,
                'message': f'Subscription created! You will receive {frequency} emails for r/{subreddit}',
                'next_email': subscription['next_send']
            })
            
        except Exception as e:
            print(f"❌ Subscription Error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def calculate_next_send_date(self, frequency):
        """Calculate next email send date"""
        now = datetime.now()
        
        if frequency == 'weekly':
            # Next Monday
            days_ahead = 0 - now.weekday()  # Monday is 0
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            next_date = now + timedelta(days=days_ahead)
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        
        elif frequency == 'monthly':
            # First day of next month
            if now.month == 12:
                next_date = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_date = now.replace(month=now.month + 1, day=1)
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0).isoformat()
        
        return (now + timedelta(days=7)).isoformat()  # Default to weekly
    
    def send_confirmation_email(self, subscription, posts):
        """Send confirmation email with current posts"""
        try:
            print(f"📧 CONFIRMATION EMAIL")
            print(f"=" * 50)
            print(f"To: {subscription['email']}")
            print(f"Subject: 🎉 Subscription Confirmed: r/{subscription['subreddit']}")
            print(f"Frequency: {subscription['frequency'].title()}")
            print(f"Next email: {subscription['next_send'][:10]}")
            print(f"Posts included:")
            
            for i, post in enumerate(posts[:5], 1):
                print(f"  {i}. {post['title'][:60]}...")
                print(f"     👤 u/{post['author']} | 👍 {post['score']} | 💬 {post['comments']}")
            
            print(f"=" * 50)
            print(f"✅ Email confirmation logged (would be sent in production)")
            
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with rate limiting"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            # Respectful delay
            time.sleep(random.uniform(1, 2))
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self.parse_reddit_json(data)
            else:
                print(f"❌ Reddit API returned {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Reddit fetch error: {e}")
            return None
    
    def parse_reddit_json(self, data):
        """Parse Reddit JSON response"""
        posts = []
        
        try:
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
            print(f"❌ Parse error: {e}")
        
        return posts
    
    def send_json_response(self, data, status_code=200):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def send_scheduled_emails():
    """Send scheduled emails to subscribers"""
    now = datetime.now()
    print(f"📅 Checking scheduled emails at {now.strftime('%Y-%m-%d %H:%M')}")
    
    if not SimpleRedditHandler.email_subscriptions:
        print("📭 No active subscriptions")
        return
    
    for subscription in SimpleRedditHandler.email_subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'])
            
            if now >= next_send:
                print(f"📧 Sending {subscription['frequency']} email to {subscription['email']} for r/{subscription['subreddit']}")
                
                # Fetch fresh posts
                handler = SimpleRedditHandler.__new__(SimpleRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                posts = handler.fetch_reddit_data(
                    subscription['subreddit'],
                    subscription['sort_type'],
                    subscription['time_filter'],
                    5
                )
                
                if posts:
                    handler.send_confirmation_email(subscription, posts)
                    
                    # Update next send date
                    subscription['next_send'] = handler.calculate_next_send_date(subscription['frequency'])
                    print(f"📅 Next email scheduled for: {subscription['next_send'][:10]}")
                else:
                    print(f
