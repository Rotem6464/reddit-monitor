#!/usr/bin/env python3
"""
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
            
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('session_token='):
                token = cookie.split('session_token=')[1].strip()
                if token:
                    return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        console.log('Login page JavaScript loading...');
        
        // Wait for DOM to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing login form...');
            
            // Check if already logged in
            if (document.cookie.includes('session_token=')) {
                console.log('User already logged in, redirecting...');
                window.location.href = '/dashboard';
                return;
            }
            
            // Add autocomplete attributes to fix the warning
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const loginForm = document.getElementById('loginForm');
            
            if (usernameInput) {
                usernameInput.setAttribute('autocomplete', 'username');
                console.log('Username input configured');
            } else {
                console.error('Username input not found');
            }
            
            if (passwordInput) {
                passwordInput.setAttribute('autocomplete', 'current-password');
                console.log('Password input configured');
            } else {
                console.error('Password input not found');
            }
            
            if (loginForm) {
                console.log('Adding form submit handler...');
                loginForm.addEventListener('submit', async function(e) {
                    console.log('Form submitted');
                    e.preventDefault(); // Prevent form from refreshing page
                    
                    const username = usernameInput ? usernameInput.value.trim() : '';
                    const password = passwordInput ? passwordInput.value.trim() : '';
                    
                    console.log('Login attempt for username:', username);
                    
                    if (!username || !password) {
                        showStatus('Please enter both username and password', 'error');
                        return;
                    }
                    
                    showStatus('Logging in...', 'loading');
                    
                    try {
                        console.log('Sending login request...');
                        const response = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ username, password })
                        });
                        
                        console.log('Login response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        console.log('Login result:', result);
                        
                        if (result.success) {
                            // Set session cookie
                            document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                            showStatus('Login successful! Redirecting...', 'success');
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1000);
                        } else {
                            showStatus(result.error || 'Login failed', 'error');
                        }
                    } catch (error) {
                        console.error('Login error:', error);
                        showStatus('Login failed. Please try again.', 'error');
                    }
                });
                console.log('Form handler added successfully');
            } else {
                console.error('Login form not found');
            }
        });
        
        function showStatus(message, type) {
            console.log('Showing status:', message, type);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.className = `status ${type}`;
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
            } else {
                console.error('Status div not found');
                alert(message); // Fallback
            }
        }
        
        // Test if JavaScript is working
        console.log('Login page JavaScript loaded successfully');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Focus on just one subreddit for detailed debugging
            subreddit = 'programming'
            
            print(f"🧪 Detailed test for r/{subreddit}")
            print("=" * 50)
            
            posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 3)
            
            result = {
                'subreddit': subreddit,
                'success': posts is not None,
                'posts_count': len(posts) if posts else 0,
                'error': error,
                'posts': posts[:2] if posts else []  # Include sample posts
            }
            
            print(f"🔍 Final result: {result}")
            print("=" * 50)
            
            self.send_json_response({
                'success': True,
                'test_result': result,
                'message': 'Detailed Reddit test completed - check logs for full debug info'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data using multiple methods"""
        
        # Method 1: Try RSS first
        posts, error = self.fetch_reddit_rss(subreddit, sort_type, time_filter, limit)
        if posts:
            return posts, None
        
        # Method 2: Try JSON with different approach
        print(f"📊 RSS failed ({error}), trying alternative methods...")
        
        # Try the simplest possible approach - basic JSON
        try:
            url = f"https://www.reddit.com/r/{subreddit}.json?limit={limit}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; RedditBot/1.0; +http://example.com/bot)',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }
            
            print(f"📊 Trying simple JSON: {url}")
            response = requests.get(url, headers=headers, timeout=15)
            print(f"📈 Simple JSON response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                if posts:
                    print(f"✅ Simple JSON worked! Got {len(posts)} posts")
                    return posts, None
            
        except Exception as e:
            print(f"❌ Simple JSON failed: {e}")
        
        # Method 3: Use a working public Reddit proxy/mirror
        try:
            # This is a public Reddit mirror that often works when Reddit blocks IPs
            url = f"https://libredd.it/r/{subreddit}.json?limit={limit}"
            
            headers = {'User-Agent': 'RedditMonitor/1.0'}
            
            print(f"📊 Trying Libredd mirror: {url}")
            response = requests.get(url, headers=headers, timeout=15)
            print(f"📈 Libredd response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                if posts:
                    print(f"✅ Libredd worked! Got {len(posts)} posts")
                    return posts, None
                    
        except Exception as e:
            print(f"❌ Libredd failed: {e}")
        
        return None, "All Reddit access methods failed - Reddit may be blocking cloud IPs"
    
    def fetch_reddit_rss(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit RSS feeds"""
        try:
            # Build RSS URL
            if sort_type == 'hot':
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            elif sort_type == 'new':
                url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
            elif sort_type == 'top':
                time_param = 'week' if time_filter == 'week' else time_filter
                url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t={time_param}&limit={limit}"
            else:
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            
            print(f"📊 Fetching RSS: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; RedditRSSBot/1.0)',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            print(f"📈 RSS response: {response.status_code}")
            print(f"📄 Content type: {response.headers.get('content-type', 'unknown')}")
            print(f"📄 Content length: {len(response.text)}")
            
            if response.status_code == 200 and response.text.strip():
                print(f"📝 RSS content preview: {response.text[:500]}...")
                posts = self.parse_reddit_rss(response.text, subreddit)
                return posts, None if posts else "No posts found in RSS feed"
            else:
                return None, f"RSS request failed: {response.status_code}"
                
        except Exception as e:
            print(f"❌ RSS fetch error: {e}")
            return None, f"RSS error: {str(e)}"
    
    def parse_reddit_rss(self, rss_content, subreddit):
        """Parse Reddit RSS feed"""
        try:
            import xml.etree.ElementTree as ET
            import re
            from html import unescape
            
            print(f"🔍 Parsing RSS content (length: {len(rss_content)})")
            print(f"📄 RSS preview: {rss_content[:200]}...")
            
            root = ET.fromstring(rss_content)
            posts = []
            
            # Reddit RSS can have different structures, try both
            # Structure 1: Standard RSS with <item> elements
            items = root.findall('.//item')
            if not items:
                # Structure 2: Atom feed with <entry> elements
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                print(f"📋 Found {len(items)} Atom entries")
            else:
                print(f"📋 Found {len(items)} RSS items")
            
            for i, item in enumerate(items[:5], 1):  # Limit to 5 posts
                try:
                    # Try RSS structure first
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    description_elem = item.find('description')
                    
                    # If no title found, try Atom structure
                    if title_elem is None:
                        title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                        link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
                        description_elem = item.find('.//{http://www.w3.org/2005/Atom}content')
                    
                    if title_elem is not None and title_elem.text:
                        title = unescape(title_elem.text.strip())
                        
                        # Get link
                        if link_elem is not None:
                            if hasattr(link_elem, 'attrib') and 'href' in link_elem.attrib:
                                link = link_elem.attrib['href']  # Atom style
                            else:
                                link = link_elem.text or ""  # RSS style
                        else:
                            link = ""
                        
                        # Get description/content
                        description = ""
                        if description_elem is not None and description_elem.text:
                            description = description_elem.text
                        
                        # Extract author from title (Reddit RSS puts it there)
                        # Format: "Title by /u/username"
                        author_match = re.search(r'by /u/([^\s\]]+)', title + " " + description)
                        if not author_match:
                            author_match = re.search(r'/u/([^\s\]<]+)', title + " " + description)
                        author = author_match.group(1) if author_match else "unknown"
                        
                        # Extract score and comments from description
                        score = 0
                        comments = 0
                        
                        if description:
                            score_match = re.search(r'(\d+)\s*points?', description, re.IGNORECASE)
                            score = int(score_match.group(1)) if score_match else 0
                            
                            comments_match = re.search(r'(\d+)\s*comments?', description, re.IGNORECASE)
                            comments = int(comments_match.group(1)) if comments_match else 0
                        
                        # Clean up title (remove "by /u/username" part)
                        title_clean = re.sub(r'\s*by /u/[^\s\]]+.*
    
    def fetch_reddit_json_fallback(self, subreddit, sort_type, time_filter, limit):
        """Fallback to JSON API (likely to be blocked but worth trying)"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.json?limit={limit}"
            if time_filter != 'all' and sort_type in ['top', 'controversial']:
                url += f"&t={time_filter}"
            
            headers = {
                'User-Agent': 'RedditMonitor/1.0 (Educational Use)',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                return posts, None
            else:
                return None, f"Reddit API blocked (status {response.status_code})"
                
        except Exception as e:
            return None, f"Reddit API unavailable: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
        print("📊 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        server.server_close()
        
    except Exception as e:
        print(f"❌ Server error: {e}")

if __name__ == "__main__":
    main(), '', title).strip()
                        if not title_clean:
                            title_clean = title
                        
                        post = {
                            'position': i,
                            'title': title_clean,
                            'author': author,
                            'score': score,
                            'comments': comments,
                            'url': link,
                            'created': 'RSS',
                            'subreddit': subreddit
                        }
                        posts.append(post)
                        print(f"✅ Parsed post {i}: {title_clean[:50]}... by u/{author}")
                    
                except Exception as e:
                    print(f"⚠️ Error parsing item {i}: {e}")
                    continue
            
            print(f"📊 Total posts parsed: {len(posts)}")
            return posts
            
        except ET.ParseError as e:
            print(f"❌ XML parsing error: {e}")
            print(f"📄 Raw content preview: {rss_content[:500]}")
            return []
        except Exception as e:
            print(f"❌ RSS parsing error: {e}")
            return []
    
    def fetch_reddit_json_fallback(self, subreddit, sort_type, time_filter, limit):
        """Fallback to JSON API (likely to be blocked but worth trying)"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.json?limit={limit}"
            if time_filter != 'all' and sort_type in ['top', 'controversial']:
                url += f"&t={time_filter}"
            
            headers = {
                'User-Agent': 'RedditMonitor/1.0 (Educational Use)',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                return posts, None
            else:
                return None, f"Reddit API blocked (status {response.status_code})"
                
        except Exception as e:
            return None, f"Reddit API unavailable: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
            
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('session_token='):
                token = cookie.split('session_token=')[1].strip()
                if token:
                    return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        console.log('Login page JavaScript loading...');
        
        // Wait for DOM to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing login form...');
            
            // Check if already logged in
            if (document.cookie.includes('session_token=')) {
                console.log('User already logged in, redirecting...');
                window.location.href = '/dashboard';
                return;
            }
            
            // Add autocomplete attributes to fix the warning
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const loginForm = document.getElementById('loginForm');
            
            if (usernameInput) {
                usernameInput.setAttribute('autocomplete', 'username');
                console.log('Username input configured');
            } else {
                console.error('Username input not found');
            }
            
            if (passwordInput) {
                passwordInput.setAttribute('autocomplete', 'current-password');
                console.log('Password input configured');
            } else {
                console.error('Password input not found');
            }
            
            if (loginForm) {
                console.log('Adding form submit handler...');
                loginForm.addEventListener('submit', async function(e) {
                    console.log('Form submitted');
                    e.preventDefault(); // Prevent form from refreshing page
                    
                    const username = usernameInput ? usernameInput.value.trim() : '';
                    const password = passwordInput ? passwordInput.value.trim() : '';
                    
                    console.log('Login attempt for username:', username);
                    
                    if (!username || !password) {
                        showStatus('Please enter both username and password', 'error');
                        return;
                    }
                    
                    showStatus('Logging in...', 'loading');
                    
                    try {
                        console.log('Sending login request...');
                        const response = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ username, password })
                        });
                        
                        console.log('Login response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        console.log('Login result:', result);
                        
                        if (result.success) {
                            // Set session cookie
                            document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                            showStatus('Login successful! Redirecting...', 'success');
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1000);
                        } else {
                            showStatus(result.error || 'Login failed', 'error');
                        }
                    } catch (error) {
                        console.error('Login error:', error);
                        showStatus('Login failed. Please try again.', 'error');
                    }
                });
                console.log('Form handler added successfully');
            } else {
                console.error('Login form not found');
            }
        });
        
        function showStatus(message, type) {
            console.log('Showing status:', message, type);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.className = `status ${type}`;
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
            } else {
                console.error('Status div not found');
                alert(message); // Fallback
            }
        }
        
        // Test if JavaScript is working
        console.log('Login page JavaScript loaded successfully');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            # Also test a direct RSS fetch for debugging
            print(f"🔍 Testing direct RSS fetch for r/programming...")
            try:
                import requests
                rss_url = "https://www.reddit.com/r/programming/.rss?limit=2"
                response = requests.get(rss_url, headers={'User-Agent': 'RedditRSSMonitor/1.0'}, timeout=10)
                print(f"📈 Direct RSS response: {response.status_code}")
                if response.status_code == 200:
                    print(f"📄 RSS content length: {len(response.text)}")
                    print(f"📝 RSS sample: {response.text[:300]}...")
                else:
                    print(f"❌ RSS failed: {response.text[:200]}")
            except Exception as e:
                print(f"❌ Direct RSS test error: {e}")
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data using RSS feeds (more reliable for cloud hosting)"""
        
        try:
            # Use RSS feeds which are less likely to be blocked
            if sort_type == 'hot':
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            elif sort_type == 'new':
                url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
            elif sort_type == 'top':
                time_param = 'week' if time_filter == 'week' else time_filter
                url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t={time_param}&limit={limit}"
            else:
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            
            print(f"📊 Fetching RSS from: {url}")
            
            headers = {
                'User-Agent': 'RedditRSSMonitor/1.0 (Educational Purpose)',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            
            time.sleep(random.uniform(1, 2))
            
            response = requests.get(url, headers=headers, timeout=15)
            print(f"📈 Reddit RSS Response: {response.status_code}")
            
            if response.status_code == 200:
                posts = self.parse_reddit_rss(response.text, subreddit)
                if posts:
                    print(f"✅ Successfully parsed {len(posts)} posts from RSS")
                    return posts, None
                else:
                    return None, "No posts found in RSS feed"
            elif response.status_code == 403:
                return None, "Subreddit is private or requires approved membership"
            elif response.status_code == 404:
                return None, "Subreddit not found"
            else:
                print(f"❌ RSS failed with {response.status_code}, trying JSON fallback...")
                # Fallback to JSON (might still be blocked but worth trying)
                return self.fetch_reddit_json_fallback(subreddit, sort_type, time_filter, limit)
                
        except Exception as e:
            print(f"❌ RSS fetch error: {e}")
            return self.fetch_reddit_json_fallback(subreddit, sort_type, time_filter, limit)
    
    def parse_reddit_rss(self, rss_content, subreddit):
        """Parse Reddit RSS feed"""
        try:
            import xml.etree.ElementTree as ET
            import re
            from html import unescape
            
            print(f"🔍 Parsing RSS content (length: {len(rss_content)})")
            print(f"📄 RSS preview: {rss_content[:200]}...")
            
            root = ET.fromstring(rss_content)
            posts = []
            
            # Reddit RSS can have different structures, try both
            # Structure 1: Standard RSS with <item> elements
            items = root.findall('.//item')
            if not items:
                # Structure 2: Atom feed with <entry> elements
                items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                print(f"📋 Found {len(items)} Atom entries")
            else:
                print(f"📋 Found {len(items)} RSS items")
            
            for i, item in enumerate(items[:5], 1):  # Limit to 5 posts
                try:
                    # Try RSS structure first
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    description_elem = item.find('description')
                    
                    # If no title found, try Atom structure
                    if title_elem is None:
                        title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
                        link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
                        description_elem = item.find('.//{http://www.w3.org/2005/Atom}content')
                    
                    if title_elem is not None and title_elem.text:
                        title = unescape(title_elem.text.strip())
                        
                        # Get link
                        if link_elem is not None:
                            if hasattr(link_elem, 'attrib') and 'href' in link_elem.attrib:
                                link = link_elem.attrib['href']  # Atom style
                            else:
                                link = link_elem.text or ""  # RSS style
                        else:
                            link = ""
                        
                        # Get description/content
                        description = ""
                        if description_elem is not None and description_elem.text:
                            description = description_elem.text
                        
                        # Extract author from title (Reddit RSS puts it there)
                        # Format: "Title by /u/username"
                        author_match = re.search(r'by /u/([^\s\]]+)', title + " " + description)
                        if not author_match:
                            author_match = re.search(r'/u/([^\s\]<]+)', title + " " + description)
                        author = author_match.group(1) if author_match else "unknown"
                        
                        # Extract score and comments from description
                        score = 0
                        comments = 0
                        
                        if description:
                            score_match = re.search(r'(\d+)\s*points?', description, re.IGNORECASE)
                            score = int(score_match.group(1)) if score_match else 0
                            
                            comments_match = re.search(r'(\d+)\s*comments?', description, re.IGNORECASE)
                            comments = int(comments_match.group(1)) if comments_match else 0
                        
                        # Clean up title (remove "by /u/username" part)
                        title_clean = re.sub(r'\s*by /u/[^\s\]]+.*
    
    def fetch_reddit_json_fallback(self, subreddit, sort_type, time_filter, limit):
        """Fallback to JSON API (likely to be blocked but worth trying)"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.json?limit={limit}"
            if time_filter != 'all' and sort_type in ['top', 'controversial']:
                url += f"&t={time_filter}"
            
            headers = {
                'User-Agent': 'RedditMonitor/1.0 (Educational Use)',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                return posts, None
            else:
                return None, f"Reddit API blocked (status {response.status_code})"
                
        except Exception as e:
            return None, f"Reddit API unavailable: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
        print("📊 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        server.server_close()
        
    except Exception as e:
        print(f"❌ Server error: {e}")

if __name__ == "__main__":
    main(), '', title).strip()
                        if not title_clean:
                            title_clean = title
                        
                        post = {
                            'position': i,
                            'title': title_clean,
                            'author': author,
                            'score': score,
                            'comments': comments,
                            'url': link,
                            'created': 'RSS',
                            'subreddit': subreddit
                        }
                        posts.append(post)
                        print(f"✅ Parsed post {i}: {title_clean[:50]}... by u/{author}")
                    
                except Exception as e:
                    print(f"⚠️ Error parsing item {i}: {e}")
                    continue
            
            print(f"📊 Total posts parsed: {len(posts)}")
            return posts
            
        except ET.ParseError as e:
            print(f"❌ XML parsing error: {e}")
            print(f"📄 Raw content preview: {rss_content[:500]}")
            return []
        except Exception as e:
            print(f"❌ RSS parsing error: {e}")
            return []
    
    def fetch_reddit_json_fallback(self, subreddit, sort_type, time_filter, limit):
        """Fallback to JSON API (likely to be blocked but worth trying)"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.json?limit={limit}"
            if time_filter != 'all' and sort_type in ['top', 'controversial']:
                url += f"&t={time_filter}"
            
            headers = {
                'User-Agent': 'RedditMonitor/1.0 (Educational Use)',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                return posts, None
            else:
                return None, f"Reddit API blocked (status {response.status_code})"
                
        except Exception as e:
            return None, f"Reddit API unavailable: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
            
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('session_token='):
                token = cookie.split('session_token=')[1].strip()
                if token:
                    return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        console.log('Login page JavaScript loading...');
        
        // Wait for DOM to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing login form...');
            
            // Check if already logged in
            if (document.cookie.includes('session_token=')) {
                console.log('User already logged in, redirecting...');
                window.location.href = '/dashboard';
                return;
            }
            
            // Add autocomplete attributes to fix the warning
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const loginForm = document.getElementById('loginForm');
            
            if (usernameInput) {
                usernameInput.setAttribute('autocomplete', 'username');
                console.log('Username input configured');
            } else {
                console.error('Username input not found');
            }
            
            if (passwordInput) {
                passwordInput.setAttribute('autocomplete', 'current-password');
                console.log('Password input configured');
            } else {
                console.error('Password input not found');
            }
            
            if (loginForm) {
                console.log('Adding form submit handler...');
                loginForm.addEventListener('submit', async function(e) {
                    console.log('Form submitted');
                    e.preventDefault(); // Prevent form from refreshing page
                    
                    const username = usernameInput ? usernameInput.value.trim() : '';
                    const password = passwordInput ? passwordInput.value.trim() : '';
                    
                    console.log('Login attempt for username:', username);
                    
                    if (!username || !password) {
                        showStatus('Please enter both username and password', 'error');
                        return;
                    }
                    
                    showStatus('Logging in...', 'loading');
                    
                    try {
                        console.log('Sending login request...');
                        const response = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ username, password })
                        });
                        
                        console.log('Login response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        console.log('Login result:', result);
                        
                        if (result.success) {
                            // Set session cookie
                            document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                            showStatus('Login successful! Redirecting...', 'success');
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1000);
                        } else {
                            showStatus(result.error || 'Login failed', 'error');
                        }
                    } catch (error) {
                        console.error('Login error:', error);
                        showStatus('Login failed. Please try again.', 'error');
                    }
                });
                console.log('Form handler added successfully');
            } else {
                console.error('Login form not found');
            }
        });
        
        function showStatus(message, type) {
            console.log('Showing status:', message, type);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.className = `status ${type}`;
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
            } else {
                console.error('Status div not found');
                alert(message); // Fallback
            }
        }
        
        // Test if JavaScript is working
        console.log('Login page JavaScript loaded successfully');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data using RSS feeds (more reliable for cloud hosting)"""
        
        try:
            # Use RSS feeds which are less likely to be blocked
            if sort_type == 'hot':
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            elif sort_type == 'new':
                url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
            elif sort_type == 'top':
                time_param = 'week' if time_filter == 'week' else time_filter
                url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t={time_param}&limit={limit}"
            else:
                url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            
            print(f"📊 Fetching RSS from: {url}")
            
            headers = {
                'User-Agent': 'RedditRSSMonitor/1.0 (Educational Purpose)',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            
            time.sleep(random.uniform(1, 2))
            
            response = requests.get(url, headers=headers, timeout=15)
            print(f"📈 Reddit RSS Response: {response.status_code}")
            
            if response.status_code == 200:
                posts = self.parse_reddit_rss(response.text, subreddit)
                if posts:
                    print(f"✅ Successfully parsed {len(posts)} posts from RSS")
                    return posts, None
                else:
                    return None, "No posts found in RSS feed"
            elif response.status_code == 403:
                return None, "Subreddit is private or requires approved membership"
            elif response.status_code == 404:
                return None, "Subreddit not found"
            else:
                print(f"❌ RSS failed with {response.status_code}, trying JSON fallback...")
                # Fallback to JSON (might still be blocked but worth trying)
                return self.fetch_reddit_json_fallback(subreddit, sort_type, time_filter, limit)
                
        except Exception as e:
            print(f"❌ RSS fetch error: {e}")
            return self.fetch_reddit_json_fallback(subreddit, sort_type, time_filter, limit)
    
    def parse_reddit_rss(self, rss_content, subreddit):
        """Parse Reddit RSS feed"""
        import xml.etree.ElementTree as ET
        import re
        from html import unescape
        
        try:
            root = ET.fromstring(rss_content)
            posts = []
            
            # Find all item elements
            items = root.findall('.//item')
            
            for i, item in enumerate(items[:5], 1):  # Limit to 5 posts
                title_elem = item.find('title')
                link_elem = item.find('link')
                description_elem = item.find('description')
                
                if title_elem is not None and link_elem is not None:
                    title = unescape(title_elem.text or "No title")
                    link = link_elem.text or ""
                    description = description_elem.text or "" if description_elem is not None else ""
                    
                    # Extract author from description (it's usually in there)
                    author_match = re.search(r'submitted by.*?/u/([^\s<]+)', description)
                    author = author_match.group(1) if author_match else "unknown"
                    
                    # Extract score if available (might not be in RSS)
                    score_match = re.search(r'(\d+) points?', description)
                    score = int(score_match.group(1)) if score_match else 0
                    
                    # Extract comments count
                    comments_match = re.search(r'(\d+) comments?', description)
                    comments = int(comments_match.group(1)) if comments_match else 0
                    
                    post = {
                        'position': i,
                        'title': title,
                        'author': author,
                        'score': score,
                        'comments': comments,
                        'url': link,
                        'created': 'RSS',
                        'subreddit': subreddit
                    }
                    posts.append(post)
            
            return posts
            
        except Exception as e:
            print(f"❌ RSS parsing error: {e}")
            return []
    
    def fetch_reddit_json_fallback(self, subreddit, sort_type, time_filter, limit):
        """Fallback to JSON API (likely to be blocked but worth trying)"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/.json?limit={limit}"
            if time_filter != 'all' and sort_type in ['top', 'controversial']:
                url += f"&t={time_filter}"
            
            headers = {
                'User-Agent': 'RedditMonitor/1.0 (Educational Use)',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                return posts, None
            else:
                return None, f"Reddit API blocked (status {response.status_code})"
                
        except Exception as e:
            return None, f"Reddit API unavailable: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        if not cookie_header:
            return None
            
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('session_token='):
                token = cookie.split('session_token=')[1].strip()
                if token:
                    return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        console.log('Login page JavaScript loading...');
        
        // Wait for DOM to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing login form...');
            
            // Check if already logged in
            if (document.cookie.includes('session_token=')) {
                console.log('User already logged in, redirecting...');
                window.location.href = '/dashboard';
                return;
            }
            
            // Add autocomplete attributes to fix the warning
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const loginForm = document.getElementById('loginForm');
            
            if (usernameInput) {
                usernameInput.setAttribute('autocomplete', 'username');
                console.log('Username input configured');
            } else {
                console.error('Username input not found');
            }
            
            if (passwordInput) {
                passwordInput.setAttribute('autocomplete', 'current-password');
                console.log('Password input configured');
            } else {
                console.error('Password input not found');
            }
            
            if (loginForm) {
                console.log('Adding form submit handler...');
                loginForm.addEventListener('submit', async function(e) {
                    console.log('Form submitted');
                    e.preventDefault(); // Prevent form from refreshing page
                    
                    const username = usernameInput ? usernameInput.value.trim() : '';
                    const password = passwordInput ? passwordInput.value.trim() : '';
                    
                    console.log('Login attempt for username:', username);
                    
                    if (!username || !password) {
                        showStatus('Please enter both username and password', 'error');
                        return;
                    }
                    
                    showStatus('Logging in...', 'loading');
                    
                    try {
                        console.log('Sending login request...');
                        const response = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ username, password })
                        });
                        
                        console.log('Login response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        console.log('Login result:', result);
                        
                        if (result.success) {
                            // Set session cookie
                            document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                            showStatus('Login successful! Redirecting...', 'success');
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1000);
                        } else {
                            showStatus(result.error || 'Login failed', 'error');
                        }
                    } catch (error) {
                        console.error('Login error:', error);
                        showStatus('Login failed. Please try again.', 'error');
                    }
                });
                console.log('Form handler added successfully');
            } else {
                console.error('Login form not found');
            }
        });
        
        function showStatus(message, type) {
            console.log('Showing status:', message, type);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.className = `status ${type}`;
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
            } else {
                console.error('Status div not found');
                alert(message); // Fallback
            }
        }
        
        // Test if JavaScript is working
        console.log('Login page JavaScript loaded successfully');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling and fallbacks"""
        
        # Try multiple approaches if the first fails
        approaches = [
            # Approach 1: Standard JSON endpoint
            {
                'url_template': 'https://www.reddit.com/r/{}/{}/.json?limit={}',
                'headers': {
                    'User-Agent': 'RedditMonitor/1.0',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            },
            # Approach 2: Old Reddit with different User-Agent
            {
                'url_template': 'https://old.reddit.com/r/{}/{}/.json?limit={}',
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (compatible; RedditBot/1.0)',
                    'Accept': 'application/json'
                }
            },
            # Approach 3: www.reddit.com with browser-like headers
            {
                'url_template': 'https://www.reddit.com/r/{}/{}/.json?limit={}',
                'headers': {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
            }
        ]
        
        for i, approach in enumerate(approaches, 1):
            try:
                url = approach['url_template'].format(subreddit, sort_type, limit)
                if time_filter != 'all' and sort_type in ['top', 'controversial']:
                    url += f"&t={time_filter}"
                
                print(f"📊 Attempt {i}/3: Fetching from: {url}")
                print(f"🔄 Using approach: {approach['headers']['User-Agent'][:30]}...")
                
                # Respectful delay
                time.sleep(random.uniform(1.5, 3.0))
                
                response = requests.get(
                    url, 
                    headers=approach['headers'], 
                    timeout=20,
                    allow_redirects=True
                )
                
                print(f"📈 Reddit API Response (attempt {i}): {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        posts = self.parse_reddit_json(data)
                        if posts:  # Only return if we got actual posts
                            print(f"✅ Successfully parsed {len(posts)} posts on attempt {i}")
                            return posts, None
                        else:
                            print(f"⚠️ No posts found in response on attempt {i}")
                            continue
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON decode error on attempt {i}: {e}")
                        continue
                        
                elif response.status_code == 403:
                    print(f"❌ 403 Forbidden on attempt {i}")
                    if i == len(approaches):  # Last attempt
                        return None, "Subreddit is private, requires approved membership, or access is blocked"
                    continue
                    
                elif response.status_code == 404:
                    print(f"❌ 404 Not Found on attempt {i}")
                    return None, "Subreddit not found"
                    
                elif response.status_code == 429:
                    print(f"❌ 429 Rate Limited on attempt {i}")
                    if i < len(approaches):
                        print(f"Waiting longer before next attempt...")
                        time.sleep(random.uniform(3, 6))
                        continue
                    return None, "Rate limit exceeded - try again later"
                    
                elif response.status_code == 502:
                    print(f"❌ 502 Bad Gateway on attempt {i} - Reddit server issues")
                    if i < len(approaches):
                        time.sleep(random.uniform(2, 4))
                        continue
                    return None, "Reddit servers are having issues - try again later"
                    
                elif response.status_code == 503:
                    print(f"❌ 503 Service Unavailable on attempt {i}")
                    if i < len(approaches):
                        time.sleep(random.uniform(2, 4))
                        continue
                    return None, "Reddit is temporarily unavailable"
                    
                else:
                    print(f"❌ Unexpected status code on attempt {i}: {response.status_code}")
                    print(f"Response preview: {response.text[:200]}")
                    if i < len(approaches):
                        continue
                    return None, f"Reddit API returned status {response.status_code}"
                
            except requests.exceptions.Timeout:
                print(f"❌ Request timeout on attempt {i}")
                if i < len(approaches):
                    continue
                return None, "Request timeout - Reddit may be slow"
                
            except requests.exceptions.ConnectionError:
                print(f"❌ Connection error on attempt {i}")
                if i < len(approaches):
                    time.sleep(2)
                    continue
                return None, "Connection error - check internet connection"
                
            except Exception as e:
                print(f"❌ Unexpected error on attempt {i}: {e}")
                if i < len(approaches):
                    continue
                return None, f"Network error: {str(e)}"
        
        # If all approaches failed
        return None, "All connection attempts failed - Reddit may be blocking requests"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        console.log('Login page JavaScript loading...');
        
        // Wait for DOM to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing login form...');
            
            // Check if already logged in
            if (document.cookie.includes('session_token=')) {
                console.log('User already logged in, redirecting...');
                window.location.href = '/dashboard';
                return;
            }
            
            // Add autocomplete attributes to fix the warning
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const loginForm = document.getElementById('loginForm');
            
            if (usernameInput) {
                usernameInput.setAttribute('autocomplete', 'username');
                console.log('Username input configured');
            } else {
                console.error('Username input not found');
            }
            
            if (passwordInput) {
                passwordInput.setAttribute('autocomplete', 'current-password');
                console.log('Password input configured');
            } else {
                console.error('Password input not found');
            }
            
            if (loginForm) {
                console.log('Adding form submit handler...');
                loginForm.addEventListener('submit', async function(e) {
                    console.log('Form submitted');
                    e.preventDefault(); // Prevent form from refreshing page
                    
                    const username = usernameInput ? usernameInput.value.trim() : '';
                    const password = passwordInput ? passwordInput.value.trim() : '';
                    
                    console.log('Login attempt for username:', username);
                    
                    if (!username || !password) {
                        showStatus('Please enter both username and password', 'error');
                        return;
                    }
                    
                    showStatus('Logging in...', 'loading');
                    
                    try {
                        console.log('Sending login request...');
                        const response = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ username, password })
                        });
                        
                        console.log('Login response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        
                        const result = await response.json();
                        console.log('Login result:', result);
                        
                        if (result.success) {
                            // Set session cookie
                            document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                            showStatus('Login successful! Redirecting...', 'success');
                            setTimeout(() => {
                                window.location.href = '/dashboard';
                            }, 1000);
                        } else {
                            showStatus(result.error || 'Login failed', 'error');
                        }
                    } catch (error) {
                        console.error('Login error:', error);
                        showStatus('Login failed. Please try again.', 'error');
                    }
                });
                console.log('Form handler added successfully');
            } else {
                console.error('Login form not found');
            }
        });
        
        function showStatus(message, type) {
            console.log('Showing status:', message, type);
            const statusDiv = document.getElementById('status');
            if (statusDiv) {
                statusDiv.className = `status ${type}`;
                statusDiv.textContent = message;
                statusDiv.style.display = 'block';
            } else {
                console.error('Status div not found');
                alert(message); // Fallback
            }
        }
        
        // Test if JavaScript is working
        console.log('Login page JavaScript loaded successfully');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling and anti-blocking measures"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            # Longer respectful delay to avoid rate limiting
            time.sleep(random.uniform(2, 4))
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }
            
            print(f"📊 Attempting to fetch from: {url}")
            print(f"🔄 Using User-Agent: {headers['User-Agent'][:50]}...")
            
            response = requests.get(url, headers=headers, timeout=15)
            
            print(f"📈 Reddit API Response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                print(f"✅ Successfully parsed {len(posts)} posts")
                return posts, None
            elif response.status_code == 403:
                print(f"❌ 403 Forbidden - Subreddit may be private or blocked")
                return None, "Subreddit is private, requires approved membership, or access is blocked"
            elif response.status_code == 404:
                print(f"❌ 404 Not Found - Subreddit doesn't exist")
                return None, "Subreddit not found"
            elif response.status_code == 429:
                print(f"❌ 429 Rate Limited - Too many requests")
                return None, "Rate limit exceeded - try again later"
            elif response.status_code == 503:
                print(f"❌ 503 Service Unavailable - Reddit is down")
                return None, "Reddit is temporarily unavailable"
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                print(f"Response content: {response.text[:200]}")
                return None, f"Reddit API returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"❌ Request timeout for r/{subreddit}")
            return None, "Request timeout - Reddit may be slow"
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error for r/{subreddit}")
            return None, "Connection error - check internet connection"
        except Exception as e:
            print(f"❌ Reddit fetch error for r/{subreddit}: {e}")
            return None, f"Network error: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" autocomplete="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" autocomplete="current-password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();
            
            if (!username || !password) {
                showStatus('Please enter both username and password', 'error');
                return;
            }
            
            showStatus('Logging in...', 'loading');
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    // Set session cookie
                    document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}; SameSite=Lax`;
                    showStatus('Login successful! Redirecting...', 'success');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 1000);
                } else {
                    showStatus(result.error || 'Login failed', 'error');
                }
            } catch (error) {
                console.error('Login error:', error);
                showStatus('Login failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
        
        // Add autocomplete attributes to fix the warning
        document.getElementById('username').setAttribute('autocomplete', 'username');
        document.getElementById('password').setAttribute('autocomplete', 'current-password');
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent form from refreshing page
            
            const username = document.getElementById('username').value.trim();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (!username || !email || !password || !confirmPassword) {
                showStatus('Please fill in all fields', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'loading');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ username, email, password })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error || 'Registration failed', 'error');
                }
            } catch (error) {
                console.error('Registration error:', error);
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling and anti-blocking measures"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            # Longer respectful delay to avoid rate limiting
            time.sleep(random.uniform(2, 4))
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }
            
            print(f"📊 Attempting to fetch from: {url}")
            print(f"🔄 Using User-Agent: {headers['User-Agent'][:50]}...")
            
            response = requests.get(url, headers=headers, timeout=15)
            
            print(f"📈 Reddit API Response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                print(f"✅ Successfully parsed {len(posts)} posts")
                return posts, None
            elif response.status_code == 403:
                print(f"❌ 403 Forbidden - Subreddit may be private or blocked")
                return None, "Subreddit is private, requires approved membership, or access is blocked"
            elif response.status_code == 404:
                print(f"❌ 404 Not Found - Subreddit doesn't exist")
                return None, "Subreddit not found"
            elif response.status_code == 429:
                print(f"❌ 429 Rate Limited - Too many requests")
                return None, "Rate limit exceeded - try again later"
            elif response.status_code == 503:
                print(f"❌ 503 Service Unavailable - Reddit is down")
                return None, "Reddit is temporarily unavailable"
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                print(f"Response content: {response.text[:200]}")
                return None, f"Reddit API returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"❌ Request timeout for r/{subreddit}")
            return None, "Request timeout - Reddit may be slow"
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error for r/{subreddit}")
            return None, "Connection error - check internet connection"
        except Exception as e:
            print(f"❌ Reddit fetch error for r/{subreddit}: {e}")
            return None, f"Network error: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        # Suppress the datetime adapter warning
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path == '/api/test-reddit':
            self.handle_test_reddit()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            showStatus('Logging in...', 'info');
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Set session cookie
                    document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}`;
                    showStatus('Login successful! Redirecting...', 'success');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 1000);
                } else {
                    showStatus(result.error, 'error');
                }
            } catch (error) {
                showStatus('Login failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'info');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error, 'error');
                }
            } catch (error) {
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_test_reddit(self):
        """Test Reddit API without authentication for debugging"""
        try:
            # Test multiple subreddits
            test_subreddits = ['test', 'announcements', 'programming', 'technology']
            results = {}
            
            for subreddit in test_subreddits:
                print(f"🧪 Testing r/{subreddit}")
                posts, error = self.fetch_reddit_data(subreddit, 'hot', 'day', 2)
                results[subreddit] = {
                    'success': posts is not None,
                    'posts_count': len(posts) if posts else 0,
                    'error': error
                }
                print(f"Result: {results[subreddit]}")
                
                # Small delay between tests
                time.sleep(1)
            
            self.send_json_response({
                'success': True,
                'test_results': results,
                'message': 'Reddit API test completed - check logs for details'
            })
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling and anti-blocking measures"""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            if time_filter != 'all':
                url += f"&t={time_filter}"
            
            # Longer respectful delay to avoid rate limiting
            time.sleep(random.uniform(2, 4))
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'max-age=0'
            }
            
            print(f"📊 Attempting to fetch from: {url}")
            print(f"🔄 Using User-Agent: {headers['User-Agent'][:50]}...")
            
            response = requests.get(url, headers=headers, timeout=15)
            
            print(f"📈 Reddit API Response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                posts = self.parse_reddit_json(data)
                print(f"✅ Successfully parsed {len(posts)} posts")
                return posts, None
            elif response.status_code == 403:
                print(f"❌ 403 Forbidden - Subreddit may be private or blocked")
                return None, "Subreddit is private, requires approved membership, or access is blocked"
            elif response.status_code == 404:
                print(f"❌ 404 Not Found - Subreddit doesn't exist")
                return None, "Subreddit not found"
            elif response.status_code == 429:
                print(f"❌ 429 Rate Limited - Too many requests")
                return None, "Rate limit exceeded - try again later"
            elif response.status_code == 503:
                print(f"❌ 503 Service Unavailable - Reddit is down")
                return None, "Reddit is temporarily unavailable"
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                print(f"Response content: {response.text[:200]}")
                return None, f"Reddit API returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"❌ Request timeout for r/{subreddit}")
            return None, "Request timeout - Reddit may be slow"
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection error for r/{subreddit}")
            return None, "Connection error - check internet connection"
        except Exception as e:
            print(f"❌ Reddit fetch error for r/{subreddit}: {e}")
            return None, f"Network error: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration - Updated for cloud deployment
    HOST = '0.0.0.0'  # Accept connections from any IP
    try:
        # Try to get PORT from environment (required for most cloud platforms)
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    
    # For cloud deployment info
    if os.getenv('RENDER_EXTERNAL_URL'):
        print(f"🌐 Public URL: {os.getenv('RENDER_EXTERNAL_URL')}")
    elif os.getenv('RAILWAY_STATIC_URL'):
        print(f"🌐 Public URL: https://{os.getenv('RAILWAY_STATIC_URL')}")
    elif os.getenv('FLY_APP_NAME'):
        print(f"🌐 Public URL: https://{os.getenv('FLY_APP_NAME')}.fly.dev")
    else:
        print(f"🌐 Local access: http://localhost:{PORT}")
        print("⚠️  For public access, deploy to a cloud platform")
    
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Multi-User Reddit Monitor - Python 3.13 Compatible
User registration, login, and personal subscriptions
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
import hashlib
import secrets
import sqlite3
from pathlib import Path

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path="reddit_monitor.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subreddits TEXT NOT NULL,
                sort_type TEXT DEFAULT 'hot',
                time_filter TEXT DEFAULT 'day',
                next_send TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print("📊 Database initialized successfully")
    
    def create_user(self, username, email, password):
        """Create a new user"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return user_id, None
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                return None, "Username already exists"
            elif 'email' in str(e):
                return None, "Email already registered"
            else:
                return None, "Registration failed"
        except Exception as e:
            return None, f"Database error: {str(e)}"
    
    def authenticate_user(self, username, password):
        """Authenticate user login"""
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, username, email FROM users 
                WHERE username = ? AND password_hash = ? AND is_active = 1
            ''', (username, password_hash))
            
            user = cursor.fetchone()
            
            if user:
                # Update last login
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (user[0],))
                conn.commit()
            
            conn.close()
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    def create_session(self, user_id):
        """Create a new session token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)  # 7 days
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sessions (token, user_id, expires_at)
                VALUES (?, ?, ?)
            ''', (token, user_id, expires_at))
            
            conn.commit()
            conn.close()
            
            return token
        except Exception as e:
            print(f"❌ Session creation error: {e}")
            return None
    
    def get_user_from_session(self, token):
        """Get user from session token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT u.id, u.username, u.email
                FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > CURRENT_TIMESTAMP
            ''', (token,))
            
            user = cursor.fetchone()
            conn.close()
            
            return user  # (id, username, email) or None
        except Exception as e:
            print(f"❌ Session validation error: {e}")
            return None
    
    def delete_session(self, token):
        """Delete a session (logout)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Session deletion error: {e}")
            return False
    
    def create_subscription(self, user_id, subreddits, sort_type, time_filter, next_send):
        """Create a new subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Remove existing subscription for this user
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            # Create new subscription
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subreddits, sort_type, time_filter, next_send)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, json.dumps(subreddits), sort_type, time_filter, next_send))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription creation error: {e}")
            return False
    
    def get_user_subscriptions(self, user_id):
        """Get user's subscriptions"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT subreddits, sort_type, time_filter, next_send, created_at
                FROM subscriptions
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'subreddits': json.loads(result[0]),
                    'sort_type': result[1],
                    'time_filter': result[2],
                    'next_send': result[3],
                    'created_at': result[4]
                }
            return None
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            return None
    
    def delete_user_subscription(self, user_id):
        """Delete user's subscription"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Subscription deletion error: {e}")
            return False
    
    def get_all_active_subscriptions(self):
        """Get all active subscriptions for daily digest"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT s.id, s.user_id, u.email, s.subreddits, s.sort_type, s.time_filter, s.next_send
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.is_active = 1 AND u.is_active = 1
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            subscriptions = []
            for row in results:
                subscriptions.append({
                    'id': row[0],
                    'user_id': row[1],
                    'email': row[2],
                    'subreddits': json.loads(row[3]),
                    'sort_type': row[4],
                    'time_filter': row[5],
                    'next_send': row[6]
                })
            
            return subscriptions
        except Exception as e:
            print(f"❌ Get all subscriptions error: {e}")
            return []
    
    def update_subscription_next_send(self, subscription_id, next_send):
        """Update subscription next send time"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions SET next_send = ? WHERE id = ?
            ''', (next_send, subscription_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Update next send error: {e}")
            return False

class MultiUserRedditHandler(BaseHTTPRequestHandler):
    # Initialize database manager as class variable
    db = DatabaseManager()
    
    def __init__(self, *args, **kwargs):
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        ]
        super().__init__(*args, **kwargs)
    
    def get_session_user(self):
        """Get current user from session cookie"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                return self.db.get_user_from_session(token)
        return None
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/' or self.path == '/index.html':
            self.serve_main_page()
        elif self.path == '/login':
            self.serve_login_page()
        elif self.path == '/register':
            self.serve_register_page()
        elif self.path == '/dashboard':
            self.serve_dashboard()
        elif self.path.startswith('/api/reddit'):
            self.handle_reddit_api()
        elif self.path == '/api/user':
            self.handle_get_user()
        elif self.path == '/api/subscriptions':
            self.handle_get_user_subscriptions()
        elif self.path == '/logout':
            self.handle_logout()
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        if self.path == '/api/register':
            self.handle_register(post_data)
        elif self.path == '/api/login':
            self.handle_login(post_data)
        elif self.path == '/api/subscribe':
            self.handle_subscription(post_data)
        elif self.path == '/api/unsubscribe':
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
    
    def serve_main_page(self):
        """Serve the main landing page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit Monitor - Welcome</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 600px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
            text-align: center;
        }

        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 40px 30px;
        }

        .header h1 {
            font-size: 3rem;
            margin-bottom: 10px;
            font-weight: 700;
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }

        .content {
            padding: 40px 30px;
        }

        .features {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin: 30px 0;
        }

        .feature {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 15px;
            border-left: 4px solid #667eea;
        }

        .feature h3 {
            color: #495057;
            margin-bottom: 10px;
            font-size: 1.2rem;
        }

        .feature p {
            color: #6c757d;
            line-height: 1.6;
        }

        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }

        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
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

        @media (max-width: 768px) {
            .buttons {
                flex-direction: column;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit Monitor</h1>
            <p>Your Personal Reddit Digest Service</p>
        </div>

        <div class="content">
            <p style="font-size: 1.1rem; color: #6c757d; margin-bottom: 30px;">
                Get daily trending posts from your favorite subreddits delivered to your email every morning at 10:00 AM Israel time.
            </p>

            <div class="features">
                <div class="feature">
                    <h3>🎯 Multiple Subreddits</h3>
                    <p>Subscribe to multiple subreddits and get all your favorite content in one place</p>
                </div>
                
                <div class="feature">
                    <h3>📧 Daily Email Digest</h3>
                    <p>Receive top trending posts every morning with titles, links, upvotes, and comments</p>
                </div>
                
                <div class="feature">
                    <h3>🔐 Personal Account</h3>
                    <p>Create your own account to manage your subscriptions and preferences</p>
                </div>
                
                <div class="feature">
                    <h3>⚡ Real-time Updates</h3>
                    <p>Always get the freshest content with smart error handling for restricted subreddits</p>
                </div>
            </div>

            <div class="buttons">
                <a href="/login" class="btn btn-primary">🔑 Login</a>
                <a href="/register" class="btn btn-success">🚀 Sign Up Free</a>
            </div>
        </div>
    </div>

    <script>
        // Check if user is already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_login_page(self):
        """Serve the login page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
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
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #667eea;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 Login</h1>
            <p>Welcome back to Reddit Monitor</p>
        </div>

        <div class="form-container">
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Login</button>
            </form>

            <div class="links">
                <p>Don't have an account? <a href="/register">Sign up here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            showStatus('Logging in...', 'info');
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Set session cookie
                    document.cookie = `session_token=${result.token}; path=/; max-age=${7*24*60*60}`;
                    showStatus('Login successful! Redirecting...', 'success');
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 1000);
                } else {
                    showStatus(result.error, 'error');
                }
            } catch (error) {
                showStatus('Login failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_register_page(self):
        """Serve the registration page"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up - Reddit Monitor</title>
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
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            max-width: 400px;
            width: 100%;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .form-container {
            padding: 30px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #56ab2f;
            box-shadow: 0 0 0 3px rgba(86, 171, 47, 0.1);
        }

        .btn {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }

        .links {
            text-align: center;
            margin-top: 20px;
        }

        .links a {
            color: #56ab2f;
            text-decoration: none;
        }

        .links a:hover {
            text-decoration: underline;
        }

        .status {
            margin: 15px 0;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            text-align: center;
        }

        .status.error {
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }

        .status.success {
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }

        .help-text {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Sign Up</h1>
            <p>Create your Reddit Monitor account</p>
        </div>

        <div class="form-container">
            <form id="registerForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                    <div class="help-text">Choose a unique username</div>
                </div>

                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required>
                    <div class="help-text">Where we'll send your daily digests</div>
                </div>

                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                    <div class="help-text">At least 6 characters</div>
                </div>

                <div class="form-group">
                    <label for="confirmPassword">Confirm Password</label>
                    <input type="password" id="confirmPassword" name="confirmPassword" required>
                </div>

                <div id="status"></div>

                <button type="submit" class="btn">Create Account</button>
            </form>

            <div class="links">
                <p>Already have an account? <a href="/login">Login here</a></p>
                <p><a href="/">← Back to home</a></p>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            if (password !== confirmPassword) {
                showStatus('Passwords do not match', 'error');
                return;
            }
            
            if (password.length < 6) {
                showStatus('Password must be at least 6 characters', 'error');
                return;
            }
            
            showStatus('Creating account...', 'info');
            
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, email, password })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showStatus('Account created! Redirecting to login...', 'success');
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    showStatus(result.error, 'error');
                }
            } catch (error) {
                showStatus('Registration failed. Please try again.', 'error');
            }
        });
        
        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.className = `status ${type}`;
            statusDiv.textContent = message;
        }
        
        // Check if already logged in
        if (document.cookie.includes('session_token=')) {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def serve_dashboard(self):
        """Serve the user dashboard"""
        user = self.get_session_user()
        if not user:
            self.send_redirect('/login')
            return
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Reddit Monitor</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%);
            color: white;
            padding: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
        }}

        .header-left h1 {{
            font-size: 2.2rem;
            margin-bottom: 5px;
            font-weight: 700;
        }}

        .header-left p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .user-info {{
            text-align: right;
        }}

        .user-name {{
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .user-email {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .btn-logout {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}

        .btn-logout:hover {{
            background: rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.5);
        }}

        .controls {{
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }}

        .control-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: end;
        }}

        .control-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .control-group label {{
            font-weight: 600;
            color: #495057;
            font-size: 0.9rem;
        }}

        .control-group input,
        .control-group select,
        .control-group textarea {{
            padding: 12px 16px;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: white;
            font-family: inherit;
        }}

        .control-group textarea {{
            resize: vertical;
            min-height: 80px;
        }}

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {{
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }}

        .btn {{
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
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        .btn-success {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
            color: white;
        }}

        .btn-danger {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
            padding: 8px 16px;
            font-size: 0.9rem;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }}

        .status {{
            margin: 20px 0;
            padding: 15px;
            border-radius: 10px;
            font-weight: 500;
        }}

        .status.loading {{
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }}

        .status.success {{
            background: #e8f5e8;
            color: #2e7d32;
            border: 1px solid #a5d6a7;
        }}

        .status.error {{
            background: #ffebee;
            color: #c62828;
            border: 1px solid #ef9a9a;
        }}

        .posts-container {{
            padding: 30px;
        }}

        .posts-title {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 20px;
            text-align: center;
        }}

        .subreddit-section {{
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }}

        .subreddit-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .subreddit-error {{
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
        }}

        .post-card {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .post-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            border-color: #667eea;
        }}

        .post-header {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
        }}

        .post-number {{
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
        }}

        .post-title {{
            font-size: 1.3rem;
            font-weight: 600;
            color: #1a73e8;
            line-height: 1.4;
            flex: 1;
        }}

        .post-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .post-title a:hover {{
            text-decoration: underline;
        }}

        .post-meta {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .post-author {{
            color: #6c757d;
            font-size: 1rem;
            font-weight: 500;
        }}

        .post-stats {{
            display: flex;
            gap: 20px;
        }}

        .stat {{
            background: #f8f9fa;
            padding: 8px 15px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .stat.score {{
            color: #ff6b6b;
        }}

        .stat.comments {{
            color: #667eea;
        }}

        .subscription-section {{
            background: #f8f9fa;
            padding: 25px;
            border-top: 1px solid #dee2e6;
        }}

        .subscription-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.3rem;
        }}

        .subscription-item {{
            background: white;
            padding: 20px;
            margin: 15px 0;
            border-radius: 10px;
            border: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .subreddit-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}

        .tag {{
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}

        .help-text {{
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: #6c757d;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #495057;
        }}

        @media (max-width: 768px) {{
            .header {{
                flex-direction: column;
                gap: 20px;
                text-align: center;
            }}
            
            .control-row {{
                flex-direction: column;
                align-items: stretch;
            }}

            .btn {{
                align-self: stretch;
            }}

            .post-meta {{
                flex-direction: column;
                align-items: stretch;
                gap: 10px;
            }}

            .post-stats {{
                justify-content: center;
            }}

            .subscription-item {{
                flex-direction: column;
                gap: 15px;
                align-items: stretch;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>📊 Reddit Monitor</h1>
                <p>Your Personal Dashboard</p>
            </div>
            <div class="header-right">
                <div class="user-info">
                    <div class="user-name">👤 {user[1]}</div>
                    <div class="user-email">{user[2]}</div>
                </div>
                <a href="/logout" class="btn-logout">Logout</a>
            </div>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Preview Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Preview Posts" to see what you'll receive in your daily digest!</p>
                </div>
            </div>
        </div>

        <div class="subscription-section" id="subscriptionSection">
            <h3>📧 Daily Email Subscription</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Subscribe to get daily top trending posts delivered every morning at 10:00 AM Israel time
            </p>
            
            <button class="btn btn-success" id="subscribeBtn" onclick="subscribeToDaily()" style="display: none;">
                📧 Subscribe to Daily Digest
            </button>
            
            <div id="subscriptionStatus"></div>
            <div id="currentSubscription"></div>
        </div>
    </div>

    <script>
        let currentPosts = {{}};
        let currentConfig = {{}};
        let currentUser = null;

        // Load user info and subscription on page load
        window.onload = async () => {{
            await loadUserInfo();
            await loadCurrentSubscription();
        }};

        async function loadUserInfo() {{
            try {{
                const response = await fetch('/api/user');
                const result = await response.json();
                
                if (result.success) {{
                    currentUser = result.user;
                }} else {{
                    window.location.href = '/login';
                }}
            }} catch (error) {{
                console.error('Failed to load user info:', error);
                window.location.href = '/login';
            }}
        }}

        async function loadCurrentSubscription() {{
            try {{
                const response = await fetch('/api/subscriptions');
                const result = await response.json();
                
                if (result.success && result.subscription) {{
                    displayCurrentSubscription(result.subscription);
                }} else {{
                    showNoSubscription();
                }}
            }} catch (error) {{
                console.error('Failed to load subscription:', error);
            }}
        }}

        function displayCurrentSubscription(subscription) {{
            const container = document.getElementById('currentSubscription');
            const nextSend = new Date(subscription.next_send).toLocaleDateString();
            
            container.innerHTML = `
                <div class="subscription-item">
                    <div>
                        <strong>✅ Active Daily Digest</strong>
                        <div class="subreddit-tags">
                            ${{subscription.subreddits.map(sr => `<span class="tag">r/${{sr}}</span>`).join('')}}
                        </div>
                        <small>Next email: ${{nextSend}} at 10:00 AM Israel time</small><br>
                        <small>Sort: ${{subscription.sort_type}} | Time: ${{subscription.time_filter}}</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribeFromDaily()">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `;
            
            // Pre-fill form with current subscription
            document.getElementById('subreddits').value = subscription.subreddits.join(', ');
            document.getElementById('sortType').value = subscription.sort_type;
            document.getElementById('timeFilter').value = subscription.time_filter;
        }}

        function showNoSubscription() {{
            const container = document.getElementById('currentSubscription');
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #6c757d;">
                    <p>📭 No active subscription</p>
                    <p>Preview posts above and then subscribe to get daily emails!</p>
                </div>
            `;
            document.getElementById('subscribeBtn').style.display = 'block';
        }}

        function showStatus(message, type = 'loading', containerId = 'status') {{
            const statusDiv = document.getElementById(containerId);
            statusDiv.className = `status ${{type}}`;
            statusDiv.textContent = message;
            statusDiv.style.display = 'block';
        }}

        function hideStatus(containerId = 'status') {{
            document.getElementById(containerId).style.display = 'none';
        }}

        async function fetchPosts() {{
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {{
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }}

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {{
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            }};

            showStatus(`🔍 Fetching top posts from ${{subreddits.length}} subreddit(s)...`, 'loading');

            try {{
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {{}};
                
                results.forEach((result, index) => {{
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {{
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    }} else {{
                        currentPosts[subreddit] = {{ error: result.error || 'Unknown error' }};
                        errors++;
                    }}
                }});

                if (totalPosts > 0) {{
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${{totalPosts}} posts from ${{subreddits.length - errors}} subreddit(s)${{errors > 0 ? ` (${{errors}} failed)` : ''}}`, 'success');
                    document.getElementById('subscribeBtn').style.display = 'block';
                }} else {{
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    displayEmptyState();
                }}

            }} catch (error) {{
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
            }}
        }}

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {{
            try {{
                const apiUrl = `/api/reddit?subreddit=${{encodeURIComponent(subreddit)}}&sort=${{sortType}}&time=${{timeFilter}}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            }} catch (error) {{
                return {{ success: false, error: 'Network error', posts: [] }};
            }}
        }}

        function displayPosts(postsData) {{
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Preview: Your Daily Digest Content</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {{
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${{subreddit}}</div>`;
                
                if (data.error) {{
                    html += `<div class="subreddit-error">
                        ❌ Error: ${{data.error}}
                        ${{data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}}
                    </div>`;
                }} else {{
                    data.forEach(post => {{
                        html += `
                        <div class="post-card">
                            <div class="post-header">
                                <div class="post-number">${{post.position}}</div>
                                <div class="post-title">
                                    <a href="${{post.url}}" target="_blank">${{post.title}}</a>
                                </div>
                            </div>
                            <div class="post-meta">
                                <div class="post-author">👤 by u/${{post.author}}</div>
                                <div class="post-stats">
                                    <div class="stat score">
                                        👍 ${{formatNumber(post.score)}}
                                    </div>
                                    <div class="stat comments">
                                        💬 ${{formatNumber(post.comments)}}
                                    </div>
                                </div>
                            </div>
                        </div>
                        `;
                    }});
                }}
                
                html += '</div>';
            }});
            
            container.innerHTML = html;
        }}

        function displayEmptyState() {{
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
                </div>
            `;
        }}

        function formatNumber(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1) + 'M';
            }} else if (num >= 1000) {{
                return (num / 1000).toFixed(1) + 'K';
            }}
            return num.toString();
        }}

        async function subscribeToDaily() {{
            if (Object.keys(currentPosts).length === 0) {{
                showStatus('Please preview posts first before subscribing', 'error', 'subscriptionStatus');
                return;
            }}

            showStatus('📧 Setting up your daily digest...', 'loading', 'subscriptionStatus');

            try {{
                const subscriptionData = {{
                    subreddits: currentConfig.subreddits,
                    sortType: currentConfig.sortType,
                    timeFilter: currentConfig.timeFilter,
                    posts: currentPosts
                }};

                const response = await fetch('/api/subscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(subscriptionData)
                }});

                const result = await response.json();

                if (result.success) {{
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${{currentConfig.subreddits.join(', ')}}`, 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                    document.getElementById('subscribeBtn').style.display = 'none';
                }} else {{
                    showStatus(`❌ Subscription failed: ${{result.error}}`, 'error', 'subscriptionStatus');
                }}

            }} catch (error) {{
                console.error('Subscription error:', error);
                showStatus('❌ Failed to set up subscription. Please try again.', 'error', 'subscriptionStatus');
            }}
        }}

        async function unsubscribeFromDaily() {{
            if (!confirm('Are you sure you want to unsubscribe from daily digests?')) {{
                return;
            }}

            try {{
                const response = await fetch('/api/unsubscribe', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ unsubscribe: true }})
                }});

                const result = await response.json();
                
                if (result.success) {{
                    showStatus('✅ Successfully unsubscribed from daily digest', 'success', 'subscriptionStatus');
                    await loadCurrentSubscription();
                }} else {{
                    showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
                }}
            }} catch (error) {{
                console.error('Unsubscribe error:', error);
                showStatus('❌ Failed to unsubscribe', 'error', 'subscriptionStatus');
            }}
        }}
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def send_redirect(self, location):
        """Send redirect response"""
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
    
    def handle_register(self, post_data):
        """Handle user registration"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            
            if not username or not email or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'All fields are required'
                })
                return
            
            if len(password) < 6:
                self.send_json_response({
                    'success': False,
                    'error': 'Password must be at least 6 characters'
                })
                return
            
            user_id, error = self.db.create_user(username, email, password)
            
            if user_id:
                print(f"👤 New user registered: {username} ({email})")
                self.send_json_response({
                    'success': True,
                    'message': 'Account created successfully!'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': error
                })
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Registration failed'
            }, 500)
    
    def handle_login(self, post_data):
        """Handle user login"""
        try:
            data = json.loads(post_data.decode())
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                self.send_json_response({
                    'success': False,
                    'error': 'Username and password are required'
                })
                return
            
            user = self.db.authenticate_user(username, password)
            
            if user:
                # Create session
                token = self.db.create_session(user[0])
                if token:
                    print(f"🔑 User logged in: {username}")
                    self.send_json_response({
                        'success': True,
                        'token': token,
                        'user': {'id': user[0], 'username': user[1], 'email': user[2]}
                    })
                else:
                    self.send_json_response({
                        'success': False,
                        'error': 'Failed to create session'
                    })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid username or password'
                })
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.send_json_response({
                'success': False,
                'error': 'Login failed'
            }, 500)
    
    def handle_get_user(self):
        """Handle get current user info"""
        user = self.get_session_user()
        if user:
            self.send_json_response({
                'success': True,
                'user': {'id': user[0], 'username': user[1], 'email': user[2]}
            })
        else:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
    
    def handle_logout(self):
        """Handle user logout"""
        cookie_header = self.headers.get('Cookie', '')
        for cookie in cookie_header.split(';'):
            if 'session_token=' in cookie:
                token = cookie.split('session_token=')[1].strip()
                self.db.delete_session(token)
                break
        
        self.send_redirect('/')
    
    def handle_subscription(self, post_data):
        """Handle subscription creation"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            data = json.loads(post_data.decode())
            subreddits = data.get('subreddits', [])
            sort_type = data.get('sortType', 'hot')
            time_filter = data.get('timeFilter', 'day')
            posts = data.get('posts', {})
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Create subscription in database
            success = self.db.create_subscription(
                user[0], subreddits, sort_type, time_filter, next_send
            )
            
            if success:
                # Send confirmation email
                subscription = {
                    'email': user[2],
                    'subreddits': subreddits,
                    'sort_type': sort_type,
                    'time_filter': time_filter,
                    'next_send': next_send
                }
                
                self.send_confirmation_email(subscription, posts)
                
                print(f"📧 Daily digest subscription created: {user[1]} ({user[2]}) for r/{', '.join(subreddits)}")
                
                self.send_json_response({
                    'success': True,
                    'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                    'next_email': next_send
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to create subscription'
                })
                
        except Exception as e:
            print(f"❌ Subscription error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def handle_unsubscribe(self, post_data):
        """Handle unsubscribe requests"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            success = self.db.delete_user_subscription(user[0])
            
            if success:
                print(f"📧 Unsubscribed: {user[1]} ({user[2]})")
                self.send_json_response({
                    'success': True,
                    'message': 'Successfully unsubscribed from daily digest'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'Failed to unsubscribe'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_get_user_subscriptions(self):
        """Handle getting user's subscriptions"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            subscription = self.db.get_user_subscriptions(user[0])
            
            self.send_json_response({
                'success': True,
                'subscription': subscription
            })
            
        except Exception as e:
            print(f"❌ Get subscriptions error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_reddit_api(self):
        """Handle Reddit API requests with authentication"""
        user = self.get_session_user()
        if not user:
            self.send_json_response({
                'success': False,
                'error': 'Not authenticated'
            }, 401)
            return
        
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 {user[1]} fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            if PYTZ_AVAILABLE:
                israel_tz = pytz.timezone('Asia/Jerusalem')
                now_israel = datetime.now(israel_tz)
                
                # Set to 10 AM today
                next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
                
                # If 10 AM today has passed, set to 10 AM tomorrow
                if now_israel >= next_send:
                    next_send = next_send + timedelta(days=1)
                
                return next_send.isoformat()
            else:
                # Fallback to UTC if timezone fails
                now = datetime.now()
                next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
                if now >= next_send:
                    next_send = next_send + timedelta(days=1)
                return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To manage your subscription, log into your Reddit Monitor dashboard.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To manage your subscription, log into your Reddit Monitor dashboard.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling"""
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
                posts = self.parse_reddit_json(data)
                return posts, None
            elif response.status_code == 403:
                return None, "Subreddit is private or requires approved membership"
            elif response.status_code == 404:
                return None, "Subreddit not found"
            elif response.status_code == 429:
                return None, "Rate limit exceeded - try again later"
            else:
                return None, f"Reddit API returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return None, "Request timeout - Reddit may be slow"
        except requests.exceptions.ConnectionError:
            return None, "Connection error - check internet connection"
        except Exception as e:
            print(f"❌ Reddit fetch error: {e}")
            return None, f"Network error: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        if PYTZ_AVAILABLE:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
        else:
            # Fallback if pytz is not available
            now_israel = datetime.now()
    except:
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    # Get database instance
    db = DatabaseManager()
    subscriptions = db.get_all_active_subscriptions()
    
    if not subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = MultiUserRedditHandler.__new__(MultiUserRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    next_send = handler.calculate_next_send_israel_time()
                    db.update_subscription_next_send(subscription['id'], next_send)
                    print(f"📅 Next email scheduled for: {next_send[:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration
    HOST = '0.0.0.0'
    try:
        PORT = int(os.getenv('PORT', 8080))
    except ValueError:
        PORT = 8080
    
    print("🚀 Starting Multi-User Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    print("=" * 50)
    
    # Check dependencies
    print("🔧 Checking dependencies:")
    try:
        import sqlite3
        print("   ✅ SQLite3 available")
    except ImportError:
        print("   ❌ SQLite3 not available")
        return
    
    if PYTZ_AVAILABLE:
        print("   ✅ Timezone support (pytz available)")
    else:
        print("   ⚠️  Timezone support limited (install pytz for proper Israel timezone)")
        print("      Run: pip install pytz")
    
    # Email configuration info
    smtp_configured = bool(os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'))
    if smtp_configured:
        print("   ✅ SMTP configured - emails will be sent")
    else:
        print("   ⚠️  SMTP not configured - emails will be logged only")
        print("      Set SMTP_USERNAME and SMTP_PASSWORD environment variables")
    
    print("=" * 50)
    print("Environment Variables:")
    print(f"  SMTP_SERVER: {os.getenv('SMTP_SERVER', 'smtp.gmail.com')}")
    print(f"  SMTP_PORT: {os.getenv('SMTP_PORT', '587')}")
    print(f"  SMTP_USERNAME: {'***' if os.getenv('SMTP_USERNAME') else 'Not set'}")
    print(f"  SMTP_PASSWORD: {'***' if os.getenv('SMTP_PASSWORD') else 'Not set'}")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    
    # Start email scheduler
    start_email_scheduler()
    
    # Start HTTP server
    try:
        server = HTTPServer((HOST, PORT), MultiUserRedditHandler)
        print(f"✅ Multi-User Reddit Monitor started successfully!")
        print(f"🌐 Visit http://localhost:{PORT} to access the service")
        print("📊 Features:")
        print("   • User registration and login system")
        print("   • Personal subscription management")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • SQLite database for user data")
        print("   • Session-based authentication")
        print("   • Enhanced error handling")
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
Enhanced Reddit Monitor - Python 3.13 Compatible
Multiple subreddits, daily emails at 10AM Israel time, better error handling
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
import pytz

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
        """Serve the enhanced HTML interface"""
        html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Reddit Monitor</title>
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
            max-width: 900px;
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
            min-width: 200px;
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
            font-family: inherit;
        }

        .control-group textarea {
            resize: vertical;
            min-height: 80px;
        }

        .control-group input:focus,
        .control-group select:focus,
        .control-group textarea:focus {
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

        .subreddit-section {
            margin-bottom: 40px;
            background: #f8f9fa;
            border-radius: 15px;
            padding: 25px;
        }

        .subreddit-title {
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .subreddit-error {
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #ef9a9a;
            margin-bottom: 20px;
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

        .subreddit-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }

        .tag {
            background: #e9ecef;
            color: #495057;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }

        .help-text {
            color: #6c757d;
            font-size: 0.9rem;
            margin-top: 5px;
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
            <h1>📊 Enhanced Reddit Monitor</h1>
            <p>Multiple subreddits + daily email digest at 10AM Israel time</p>
        </div>

        <div class="controls">
            <div class="control-row">
                <div class="control-group">
                    <label for="subreddits">📍 Subreddits (comma-separated)</label>
                    <textarea id="subreddits" placeholder="e.g., programming, technology, MachineLearning, artificial">programming, technology</textarea>
                    <div class="help-text">Enter multiple subreddits separated by commas</div>
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
                        <option value="day">Today</option>
                        <option value="week">This Week</option>
                        <option value="month">This Month</option>
                        <option value="year">This Year</option>
                    </select>
                </div>
                
                <button class="btn btn-primary" onclick="fetchPosts()">
                    🔍 Get Top Posts
                </button>
            </div>

            <div id="status"></div>
        </div>

        <div class="posts-container">
            <div id="postsContainer">
                <div class="empty-state">
                    <h3>🎯 Ready to Explore</h3>
                    <p>Enter subreddits and click "Get Top Posts" to see the best content!</p>
                </div>
            </div>
        </div>

        <div class="email-section" id="emailSection" style="display: none;">
            <h3>📧 Daily Reddit Digest - 10AM Israel Time</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Get daily top trending posts from your selected subreddits delivered every morning at 10:00 AM Israel time
            </p>
            
            <div class="email-form">
                <div class="email-group">
                    <label for="userEmail">Your Email Address</label>
                    <input type="email" id="userEmail" placeholder="your-email@example.com" value="rotemleffler@gmail.com">
                </div>
                
                <button class="btn btn-success" onclick="subscribeToAlerts()">
                    📧 Subscribe to Daily Digest
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
        let currentPosts = {};
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
            const subredditsInput = document.getElementById('subreddits').value.trim();
            if (!subredditsInput) {
                showStatus('Please enter at least one subreddit name', 'error');
                return;
            }

            const subreddits = subredditsInput.split(',').map(s => s.trim()).filter(s => s);
            
            currentConfig = {
                subreddits: subreddits,
                sortType: document.getElementById('sortType').value,
                timeFilter: document.getElementById('timeFilter').value
            };

            showStatus(`🔍 Fetching top posts from ${subreddits.length} subreddit(s)...`, 'loading');

            try {
                const promises = subreddits.map(subreddit => 
                    fetchSubredditPosts(subreddit, currentConfig.sortType, currentConfig.timeFilter)
                );
                
                const results = await Promise.all(promises);
                
                let totalPosts = 0;
                let errors = 0;
                currentPosts = {};
                
                results.forEach((result, index) => {
                    const subreddit = subreddits[index];
                    if (result.success && result.posts.length > 0) {
                        currentPosts[subreddit] = result.posts;
                        totalPosts += result.posts.length;
                    } else {
                        currentPosts[subreddit] = { error: result.error || 'Unknown error' };
                        errors++;
                    }
                });

                if (totalPosts > 0) {
                    displayPosts(currentPosts);
                    showStatus(`✅ Found ${totalPosts} posts from ${subreddits.length - errors} subreddit(s)${errors > 0 ? ` (${errors} failed)` : ''}`, 'success');
                    document.getElementById('emailSection').style.display = 'block';
                    document.getElementById('subscriptionsSection').style.display = 'block';
                    loadSubscriptions();
                } else {
                    showStatus('❌ No posts found from any subreddit. Check names and try again.', 'error');
                    document.getElementById('emailSection').style.display = 'none';
                    displayEmptyState();
                }

            } catch (error) {
                console.error('Error:', error);
                showStatus('❌ Failed to fetch posts. Please try again.', 'error');
                document.getElementById('emailSection').style.display = 'none';
            }
        }

        async function fetchSubredditPosts(subreddit, sortType, timeFilter) {
            try {
                const apiUrl = `/api/reddit?subreddit=${encodeURIComponent(subreddit)}&sort=${sortType}&time=${timeFilter}&limit=5`;
                const response = await fetch(apiUrl);
                return await response.json();
            } catch (error) {
                return { success: false, error: 'Network error', posts: [] };
            }
        }

        function displayPosts(postsData) {
            const container = document.getElementById('postsContainer');
            let html = '<h2 class="posts-title">🏆 Top Posts from Your Subreddits</h2>';
            
            Object.entries(postsData).forEach(([subreddit, data]) => {
                html += `<div class="subreddit-section">`;
                html += `<div class="subreddit-title">📍 r/${subreddit}</div>`;
                
                if (data.error) {
                    html += `<div class="subreddit-error">
                        ❌ Error: ${data.error}
                        ${data.error.includes('private') || data.error.includes('forbidden') || data.error.includes('approved') ? 
                            '<br><strong>This subreddit requires membership or approval to access.</strong>' : ''}
                    </div>`;
                } else {
                    data.forEach(post => {
                        html += `
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
                        `;
                    });
                }
                
                html += '</div>';
            });
            
            container.innerHTML = html;
        }

        function displayEmptyState() {
            const container = document.getElementById('postsContainer');
            container.innerHTML = `
                <div class="empty-state">
                    <h3>🔍 No Posts Found</h3>
                    <p>Try different subreddits or check the spelling</p>
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

            if (!email) {
                showStatus('Please enter your email address', 'error', 'emailStatus');
                return;
            }

            if (!email.includes('@')) {
                showStatus('Please enter a valid email address', 'error', 'emailStatus');
                return;
            }

            if (Object.keys(currentPosts).length === 0) {
                showStatus('Please fetch posts first before subscribing', 'error', 'emailStatus');
                return;
            }

            showStatus('📧 Setting up your daily digest...', 'loading', 'emailStatus');

            try {
                const subscriptionData = {
                    email: email,
                    subreddits: currentConfig.subreddits,
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
                    showStatus(`✅ Success! You'll receive daily digests at 10AM Israel time for: ${currentConfig.subreddits.join(', ')}`, 'success', 'emailStatus');
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
                        <strong>Daily Digest</strong> - ${sub.email}
                        <div class="subreddit-tags">
                            ${sub.subreddits.map(sr => `<span class="tag">r/${sr}</span>`).join('')}
                        </div>
                        <small>Next email: ${new Date(sub.next_send).toLocaleDateString()} at 10:00 AM Israel time</small>
                    </div>
                    <button class="btn btn-danger" onclick="unsubscribe('${sub.email}')">
                        🗑️ Unsubscribe
                    </button>
                </div>
            `).join('');
        }

        async function unsubscribe(email) {
            if (!confirm(`Are you sure you want to unsubscribe ${email} from all daily digests?`)) {
                return;
            }

            try {
                const response = await fetch('/api/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
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

        // Auto-focus on subreddits input
        document.getElementById('subreddits').focus();
    </script>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(html_content.encode())
    
    def handle_reddit_api(self):
        """Handle Reddit API requests with better error handling"""
        try:
            query_start = self.path.find('?')
            if query_start == -1:
                self.send_error(400, "Missing parameters")
                return
            
            query_string = self.path[query_start + 1:]
            params = urllib.parse.parse_qs(query_string)
            
            subreddit = params.get('subreddit', ['programming'])[0]
            sort_type = params.get('sort', ['hot'])[0]
            time_filter = params.get('time', ['day'])[0]
            limit = min(int(params.get('limit', ['5'])[0]), 5)
            
            print(f"📊 Fetching {limit} {sort_type} posts from r/{subreddit} ({time_filter})")
            
            posts, error_msg = self.fetch_reddit_data(subreddit, sort_type, time_filter, limit)
            
            if posts is not None:
                response_data = {
                    'success': True,
                    'posts': posts,
                    'total': len(posts)
                }
            else:
                response_data = {
                    'success': False,
                    'error': error_msg or 'Failed to fetch Reddit data',
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
            
            if not email:
                self.send_json_response({
                    'success': False,
                    'error': 'Email is required'
                })
                return
            
            # Remove all subscriptions for this email
            original_count = len(SimpleRedditHandler.email_subscriptions)
            SimpleRedditHandler.email_subscriptions = [
                sub for sub in SimpleRedditHandler.email_subscriptions 
                if sub['email'] != email
            ]
            
            removed_count = original_count - len(SimpleRedditHandler.email_subscriptions)
            
            if removed_count > 0:
                print(f"📧 Removed {removed_count} subscription(s) for: {email}")
                self.send_json_response({
                    'success': True,
                    'message': f'Successfully unsubscribed {email} from all digests'
                })
            else:
                self.send_json_response({
                    'success': False,
                    'error': 'No subscriptions found for this email'
                })
                
        except Exception as e:
            print(f"❌ Unsubscribe error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            }, 500)
    
    def handle_email_subscription(self, post_data):
        """Handle email subscription requests for multiple subreddits"""
        try:
            subscription_data = json.loads(post_data.decode())
            
            email = subscription_data.get('email', '').strip()
            subreddits = subscription_data.get('subreddits', [])
            sort_type = subscription_data.get('sortType', 'hot')
            time_filter = subscription_data.get('timeFilter', 'day')
            posts = subscription_data.get('posts', {})
            
            if not email or '@' not in email:
                self.send_json_response({
                    'success': False,
                    'error': 'Invalid email address'
                })
                return
            
            if not subreddits:
                self.send_json_response({
                    'success': False,
                    'error': 'At least one subreddit is required'
                })
                return
            
            # Calculate next send time (10AM Israel time)
            next_send = self.calculate_next_send_israel_time()
            
            # Store subscription
            subscription = {
                'email': email,
                'subreddits': subreddits,
                'sort_type': sort_type,
                'time_filter': time_filter,
                'subscribed_at': datetime.now().isoformat(),
                'next_send': next_send
            }
            
            # Remove existing subscription for this email
            SimpleRedditHandler.email_subscriptions = [
                sub for sub in SimpleRedditHandler.email_subscriptions 
                if sub['email'] != email
            ]
            
            # Add new subscription
            SimpleRedditHandler.email_subscriptions.append(subscription)
            
            # Send immediate confirmation
            self.send_confirmation_email(subscription, posts)
            
            print(f"📧 New daily digest subscription: {email} for r/{', '.join(subreddits)}")
            print(f"📋 Total subscriptions: {len(SimpleRedditHandler.email_subscriptions)}")
            
            self.send_json_response({
                'success': True,
                'message': f'Daily digest subscription created for {len(subreddits)} subreddit(s)!',
                'next_email': subscription['next_send']
            })
            
        except Exception as e:
            print(f"❌ Subscription Error: {e}")
            self.send_json_response({
                'success': False,
                'error': f'Subscription error: {str(e)}'
            }, 500)
    
    def calculate_next_send_israel_time(self):
        """Calculate next 10AM Israel time"""
        try:
            israel_tz = pytz.timezone('Asia/Jerusalem')
            now_israel = datetime.now(israel_tz)
            
            # Set to 10 AM today
            next_send = now_israel.replace(hour=10, minute=0, second=0, microsecond=0)
            
            # If 10 AM today has passed, set to 10 AM tomorrow
            if now_israel >= next_send:
                next_send = next_send + timedelta(days=1)
            
            return next_send.isoformat()
        except:
            # Fallback to UTC if timezone fails
            now = datetime.now()
            next_send = now.replace(hour=7, minute=0, second=0, microsecond=0)  # 10 AM Israel ≈ 7 AM UTC
            if now >= next_send:
                next_send = next_send + timedelta(days=1)
            return next_send.isoformat()
    
    def send_confirmation_email(self, subscription, posts_data):
        """Send confirmation email with current posts"""
        try:
            # Get email configuration from environment variables
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')
            smtp_password = os.getenv('SMTP_PASSWORD', '')
            
            if not smtp_username or not smtp_password:
                # If no email credentials, just log the email
                print(f"📧 DAILY DIGEST CONFIRMATION (SIMULATED)")
                print(f"=" * 60)
                print(f"To: {subscription['email']}")
                print(f"Subject: Reddit top trending posts digest")
                print(f"Subreddits: {', '.join(subscription['subreddits'])}")
                print(f"Next email: {subscription['next_send'][:16]} (Israel time)")
                print(f"Content preview:")
                
                for subreddit, data in posts_data.items():
                    if isinstance(data, list):
                        print(f"\n  📍 r/{subreddit}:")
                        for post in data[:3]:
                            print(f"    • {post['title'][:50]}...")
                            print(f"      👍 {post['score']} | 💬 {post['comments']}")
                    else:
                        print(f"\n  📍 r/{subreddit}: ❌ {data.get('error', 'Error')}")
                
                print(f"=" * 60)
                print(f"✅ Email confirmation logged (set SMTP credentials to send real emails)")
                return True
            
            # Create email content
            msg = MIMEMultipart('alternative')
            msg['Subject'] = "Reddit top trending posts digest"
            msg['From'] = smtp_username
            msg['To'] = subscription['email']
            
            # Create HTML and text versions
            html_content = self.create_digest_email_html(subscription, posts_data)
            text_content = self.create_digest_email_text(subscription, posts_data)
            
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
            
            print(f"📧 Daily digest confirmation sent to {subscription['email']}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending error: {e}")
            return False
    
    def create_digest_email_html(self, subscription, posts_data):
        """Create HTML email content for daily digest"""
        subreddits_html = ""
        
        for subreddit, data in posts_data.items():
            subreddits_html += f'<div style="margin-bottom: 30px;">'
            subreddits_html += f'<h2 style="color: #495057; border-bottom: 2px solid #667eea; padding-bottom: 10px;">📍 r/{subreddit}</h2>'
            
            if isinstance(data, list) and len(data) > 0:
                for post in data:
                    subreddits_html += f'''
                    <div style="background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 10px; border-left: 4px solid #667eea;">
                        <h3 style="margin: 0 0 10px 0; color: #1a73e8; font-size: 1.2rem;">
                            <a href="{post['url']}" style="color: #1a73e8; text-decoration: none;">{post['title']}</a>
                        </h3>
                        <div style="display: flex; justify-content: space-between; color: #6c757d; font-size: 0.9rem;">
                            <span>👤 by u/{post['author']}</span>
                            <span>👍 {post['score']} upvotes | 💬 {post['comments']} comments</span>
                        </div>
                    </div>
                    '''
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                subreddits_html += f'''
                <div style="background: #ffebee; color: #c62828; padding: 15px; border-radius: 10px; border: 1px solid #ef9a9a;">
                    ❌ {error_msg}
                    {' - This subreddit may require membership or approval.' if 'private' in error_msg.lower() or 'forbidden' in error_msg.lower() else ''}
                </div>
                '''
            
            subreddits_html += '</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Reddit Daily Digest</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ff8e53 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 2rem;">📊 Reddit Daily Digest</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Top trending posts from your subreddits</p>
                </div>
                
                <div style="padding: 30px;">
                    <p style="color: #6c757d; line-height: 1.6; margin-bottom: 30px;">
                        Good morning! Here are today's top trending posts from: <strong>{', '.join(subscription['subreddits'])}</strong>
                    </p>
                    
                    {subreddits_html}
                    
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin-top: 30px; text-align: center;">
                        <p style="margin: 0; color: #1976d2;">
                            📧 You'll receive this digest daily at 10:00 AM Israel time.<br>
                            To unsubscribe, visit the Reddit Monitor website.
                        </p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def create_digest_email_text(self, subscription, posts_data):
        """Create plain text email content for daily digest"""
        content = f"Reddit Daily Digest\n"
        content += f"Top trending posts from: {', '.join(subscription['subreddits'])}\n\n"
        
        for subreddit, data in posts_data.items():
            content += f"📍 r/{subreddit}\n"
            content += "-" * 40 + "\n"
            
            if isinstance(data, list) and len(data) > 0:
                for i, post in enumerate(data, 1):
                    content += f"{i}. {post['title']}\n"
                    content += f"   Link: {post['url']}\n"
                    content += f"   👍 {post['score']} upvotes | 💬 {post['comments']} comments | by u/{post['author']}\n\n"
            else:
                error_msg = data.get('error', 'No posts available') if isinstance(data, dict) else 'No posts available'
                content += f"❌ {error_msg}\n\n"
        
        content += "\nYou'll receive this digest daily at 10:00 AM Israel time.\n"
        content += "To unsubscribe, visit the Reddit Monitor website.\n"
        
        return content
    
    def fetch_reddit_data(self, subreddit, sort_type, time_filter, limit):
        """Fetch Reddit data with enhanced error handling"""
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
                posts = self.parse_reddit_json(data)
                return posts, None
            elif response.status_code == 403:
                return None, "Subreddit is private or requires approved membership"
            elif response.status_code == 404:
                return None, "Subreddit not found"
            elif response.status_code == 429:
                return None, "Rate limit exceeded - try again later"
            else:
                return None, f"Reddit API returned status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return None, "Request timeout - Reddit may be slow"
        except requests.exceptions.ConnectionError:
            return None, "Connection error - check internet connection"
        except Exception as e:
            print(f"❌ Reddit fetch error: {e}")
            return None, f"Network error: {str(e)}"
    
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

def send_daily_digest():
    """Send daily digest emails at 10 AM Israel time"""
    try:
        israel_tz = pytz.timezone('Asia/Jerusalem')
        now_israel = datetime.now(israel_tz)
    except:
        # Fallback if pytz is not available
        now_israel = datetime.now()
    
    print(f"📅 Checking daily digests at {now_israel.strftime('%Y-%m-%d %H:%M')} Israel time")
    
    if not SimpleRedditHandler.email_subscriptions:
        print("📭 No active subscriptions")
        return
    
    emails_sent = 0
    for subscription in SimpleRedditHandler.email_subscriptions:
        try:
            next_send = datetime.fromisoformat(subscription['next_send'].replace('Z', '+00:00'))
            
            if now_israel.replace(tzinfo=None) >= next_send.replace(tzinfo=None):
                print(f"📧 Sending daily digest to {subscription['email']} for r/{', '.join(subscription['subreddits'])}")
                
                # Create a temporary handler instance for email functionality
                handler = SimpleRedditHandler.__new__(SimpleRedditHandler)
                handler.user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                ]
                
                # Fetch posts from all subreddits
                posts_data = {}
                for subreddit in subscription['subreddits']:
                    posts, error_msg = handler.fetch_reddit_data(
                        subreddit,
                        subscription['sort_type'],
                        subscription['time_filter'],
                        5
                    )
                    
                    if posts:
                        posts_data[subreddit] = posts
                    else:
                        posts_data[subreddit] = {'error': error_msg or 'Unknown error'}
                
                if posts_data:
                    handler.send_confirmation_email(subscription, posts_data)
                    emails_sent += 1
                    
                    # Update next send date (next day at 10 AM Israel time)
                    subscription['next_send'] = handler.calculate_next_send_israel_time()
                    print(f"📅 Next email scheduled for: {subscription['next_send'][:16]}")
                else:
                    print(f"❌ No posts found for any subreddit, skipping email")
                    
        except Exception as e:
            print(f"❌ Error sending daily digest: {e}")
    
    if emails_sent > 0:
        print(f"✅ Sent {emails_sent} daily digest emails")

def schedule_daily_digest():
    """Schedule the daily digest function"""
    # Schedule daily at 10 AM
    schedule.every().day.at("10:00").do(send_daily_digest)
    
    # Also check every hour in case we missed the exact time
    schedule.every().hour.do(lambda: send_daily_digest() if datetime.now().hour == 10 else None)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_email_scheduler():
    """Start the email scheduler in a separate thread"""
    scheduler_thread = threading.Thread(target=schedule_daily_digest, daemon=True)
    scheduler_thread.start()
    print("📅 Daily digest scheduler started (10:00 AM Israel time)")

def main():
    """Main function to start the server"""
    # Configuration
    HOST = '0.0.0.0'
    PORT = int(os.getenv('PORT', 8080))
    
    print("🚀 Starting Enhanced Reddit Monitor...")
    print(f"📍 Server will run on http://{HOST}:{PORT}")
    print("=" * 50)
    
    # Check if pytz is available
    try:
        import pytz
        print("🌍 Timezone support: ✅ (pytz available)")
    except ImportError:
        print("🌍 Timezone support: ⚠️ (install pytz for proper Israel timezone)")
        print("   Run: pip install pytz")
    
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
        print(f"🌐 Visit http://localhost:{PORT} to use the Enhanced Reddit Monitor")
        print("📊 Features:")
        print("   • Multiple subreddits support")
        print("   • Daily digest emails at 10:00 AM Israel time")
        print("   • Better error handling for private/restricted subreddits")
        print("   • Enhanced email templates")
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
                    <input type="email" id="userEmail" placeholder="your-email@example.com" value="rotemleffler@gmail.com">
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
    main()
