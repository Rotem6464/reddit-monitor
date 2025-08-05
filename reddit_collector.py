#!/usr/bin/env python3
"""
Safe Reddit Data Collector
This script safely collects Reddit data without getting blocked
"""

import requests
import json
import time
import pandas as pd
from datetime import datetime

class SafeRedditCollector:
    def __init__(self):
        # Safe headers to identify our request properly
        self.headers = {
            'User-Agent': 'SafeRedditCollector/1.0 (Educational Research Tool)',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        # Delay between requests to be respectful
        self.delay = 2  # 2 seconds between requests
    
    def safe_request(self, url):
        """Make a safe request with proper delays and error handling"""
        try:
            print(f"Fetching: {url}")
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                print("✅ Success!")
                time.sleep(self.delay)  # Be respectful - wait before next request
                return response.json()
            else:
                print(f"❌ Error: Status code {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
    
    def get_subreddit_posts(self, subreddit, sort_type='hot', limit=10):
        """Get posts from a subreddit safely"""
        # Available sort types: hot, new, top, rising, controversial
        valid_sorts = ['hot', 'new', 'top', 'rising', 'controversial']
        
        if sort_type not in valid_sorts:
            print(f"❌ Invalid sort type. Use: {', '.join(valid_sorts)}")
            return None
        
        url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
        
        print(f"\n🔍 Getting {limit} {sort_type} posts from r/{subreddit}")
        print("=" * 50)
        
        data = self.safe_request(url)
        
        if not data:
            return None
        
        # Extract post information
        posts = []
        try:
            for post in data['data']['children']:
                post_data = post['data']
                posts.append({
                    'title': post_data.get('title', 'No title'),
                    'author': post_data.get('author', 'Unknown'),
                    'score': post_data.get('score', 0),
                    'num_comments': post_data.get('num_comments', 0),
                    'created_utc': post_data.get('created_utc', 0),
                    'url': post_data.get('url', ''),
                    'selftext': post_data.get('selftext', '')[:200] + '...' if post_data.get('selftext') else '',
                    'subreddit': subreddit,
                    'sort_type': sort_type
                })
        except KeyError as e:
            print(f"❌ Error parsing data: {e}")
            return None
        
        return posts
    
    def display_posts(self, posts):
        """Display posts in a nice format"""
        if not posts:
            print("No posts to display")
            return
        
        for i, post in enumerate(posts, 1):
            print(f"\n📝 Post {i}:")
            print(f"   Title: {post['title']}")
            print(f"   Author: u/{post['author']}")
            print(f"   Score: {post['score']} | Comments: {post['num_comments']}")
            if post['selftext']:
                print(f"   Text: {post['selftext']}")
            print(f"   URL: {post['url']}")
            print("-" * 40)
    
    def save_to_file(self, posts, filename=None):
        """Save posts to a CSV file"""
        if not posts:
            print("No posts to save")
            return
        
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            subreddit = posts[0]['subreddit']
            sort_type = posts[0]['sort_type']
            filename = f"reddit_{subreddit}_{sort_type}_{timestamp}.csv"
        
        df = pd.DataFrame(posts)
        df.to_csv(filename, index=False)
        print(f"💾 Saved {len(posts)} posts to: {filename}")

def main():
    """Main function to run the collector"""
    collector = SafeRedditCollector()
    
    print("🚀 Safe Reddit Data Collector")
    print("=" * 40)
    
    # Example usage - you can modify these
    subreddit = input("Enter subreddit name (e.g., 'travel'): ").strip()
    
    if not subreddit:
        subreddit = "travel"  # default
        print(f"Using default: {subreddit}")
    
    print("\nAvailable sort types:")
    print("1. hot (default)")
    print("2. new")
    print("3. top")
    print("4. rising")
    print("5. controversial")
    
    sort_choice = input("Choose sort type (1-5, or press Enter for hot): ").strip()
    
    sort_map = {'1': 'hot', '2': 'new', '3': 'top', '4': 'rising', '5': 'controversial'}
    sort_type = sort_map.get(sort_choice, 'hot')
    
    limit = input("How many posts? (1-25, default 10): ").strip()
    try:
        limit = int(limit) if limit else 10
        limit = min(max(limit, 1), 25)  # Keep between 1-25
    except ValueError:
        limit = 10
    
    print(f"\n🎯 Collecting {limit} {sort_type} posts from r/{subreddit}...")
    
    # Collect the data
    posts = collector.get_subreddit_posts(subreddit, sort_type, limit)
    
    if posts:
        # Display the posts
        collector.display_posts(posts)
        
        # Ask if user wants to save
        save = input("\n💾 Save to CSV file? (y/n): ").strip().lower()
        if save in ['y', 'yes']:
            collector.save_to_file(posts)
    
    print("\n✅ Done! Thank you for using Safe Reddit Collector!")

if __name__ == "__main__":
    main()
