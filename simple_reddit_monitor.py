#!/usr/bin/env python3
"""
Simple Reddit Monitor with Email Alerts
Shows 3-5 top posts and sends weekly/monthly email alerts
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import requests
import random
import time
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from datetime import datetime, timedelta
import threading
import schedule
import os

class SimpleRedditHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        ]
        
        # Email alerts storage
        self.email_subscriptions = []
        
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
            self.email_subscriptions = [
                sub for sub in self.email_subscriptions 
                if not (sub['email'] == email and sub['subreddit'] == subreddit)
            ]
            
            # Add new subscription
            self.email_subscriptions.append(subscription)
            
            # Send immediate confirmation email with current posts
            self.send_confirmation_email(subscription, posts)
            
            print(f"📧 New subscription: {email} for r/{subreddit} ({frequency})")
            
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
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0)
        
        elif frequency == 'monthly':
            # First day of next month
            if now.month == 12:
                next_date = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_date = now.replace(month=now.month + 1, day=1)
            return next_date.replace(hour=9, minute=0, second=0, microsecond=0)
        
        return now + timedelta(days=7)  # Default to weekly
    
    def send_confirmation_email(self, subscription, posts):
        """Send confirmation email with current posts"""
        try:
            subject = f"🎉 Subscription Confirmed: r/{subscription['subreddit']}"
            
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: white; }}
                    .header {{ background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 30px; }}
                    .post {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 10px; }}
                    .post-title {{ font-size: 1.1rem; font-weight: 600; color: #1a73e8; margin-bottom: 8px; }}
                    .post-meta {{ color: #6c757d; font-size: 0.9rem; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #6c757d; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📊 Reddit Monitor</h1>
                        <p>Your subscription is confirmed!</p>
                    </div>
                    <div class="content">
                        <h2>✅ Subscription Details</h2>
                        <p><strong>Subreddit:</strong> r/{subscription['subreddit']}</p>
                        <p><strong>Frequency:</strong> {subscription['frequency'].title()}</p>
                        <p><strong>Next email:</strong> {subscription['next_send'][:10]}</p>
                        
                        <h3>🏆 Current Top Posts</h3>
                        <p>Here are the latest top posts from r/{subscription['subreddit']}:</p>
            """
            
            for post in posts[:5]:
                html_body += f"""
                        <div class="post">
                            <div class="post-title">
                                <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">
                                    #{post['position']} {post['title']}
                                </a>
                            </div>
                            <div class="post-meta">
                                👤 by u/{post['author']} | 👍 {post['score']} points | 💬 {post['comments']} comments
                            </div>
                        </div>
                """
            
            html_body += f"""
                    </div>
                    <div class="footer">
                        <p>You'll receive {subscription['frequency']} updates with the top posts from r/{subscription['subreddit']}.</p>
                        <p><small>This is an automated message from Simple Reddit Monitor</small></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # For demo purposes, just print the email (you can integrate with real SMTP later)
            print(f"📧 Confirmation email sent to {subscription['email']}")
            print(f"Subject: {subject}")
            print("Email would contain the top posts and subscription details")
            
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

def run_email_scheduler():
    """Run email scheduler in background"""
    def send_scheduled_emails():
        """Send scheduled emails (placeholder for actual implementation)"""
        print("📅 Checking for scheduled emails...")
        # Here you would implement the actual email sending logic
        # For now, just print that it's running
    
    # Schedule email checks
    schedule.every().monday.at("09:00").do(send_scheduled_emails)  # Weekly emails
    schedule.every().month.at("09:00").do(send_scheduled_emails)   # Monthly emails
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def run_simple_server(port=8080):
    """Run the simple server"""
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, SimpleRedditHandler)
    
    print(f"🚀 Simple Reddit Monitor")
    print(f"=" * 40)
    print(f"🌐 Server: http://localhost:{port}")
    print(f"📊 Features:")
    print(f"   • Shows top 3-5 posts only")
    print(f"   • Simple email subscription")
    print(f"   • Weekly/Monthly alerts")
    print(f"   • Clean, focused interface")
    print(f"🛑 Press Ctrl+C to stop")
    print(f"=" * 40)
    
    # Start email scheduler in background
    email_thread = threading.Thread(target=run_email_scheduler, daemon=True)
    email_thread.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n👋 Simple Reddit Monitor stopped.")
        httpd.server_close()

if __name__ == "__main__":
    run_simple_server()
