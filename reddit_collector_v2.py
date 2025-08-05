#!/usr/bin/env python3
"""
Enhanced Safe Reddit Data Collector v2
This version uses multiple techniques to avoid getting blocked
"""

import requests
import json
import time
import pandas as pd
from datetime import datetime
import random

class EnhancedRedditCollector:
    def __init__(self):
        # Rotate between different realistic user agents
        self.user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]
        
        # Random delay between 3-7 seconds to appear more human
        self.min_delay = 3
        self.max_delay = 7
        
        # Session for connection reuse
        self.session = requests.Session()
    
    def get_headers(self):
        """Get randomized headers for each request"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
    
    def human_delay(self):
        """Random delay to mimic human behavior"""
        delay = random.uniform(self.min_delay, self.max_delay)
        print(f"⏳ Waiting {delay:.1f} seconds...")
        time.sleep(delay)
    
    def safe_request(self, url):
        """Make a very safe request with enhanced anti-detection"""
        try:
            print(f"🌐 Accessing: {url}")
            
            # Add random delay before request
            if hasattr(self, '_made_request'):
                self.human_delay()
            
            headers = self.get_headers()
            
            response = self.session.get(
                url, 
                headers=headers, 
                timeout=15,
                allow_redirects=True
            )
            
            self._made_request = True
            
            if response.status_code == 200:
                print("✅ Success!")
                return response.json()
            elif response.status_code == 403:
                print("❌ Access denied (403) - Reddit may be blocking automated requests")
                print("💡 Try again later or use a different subreddit")
                return None
            elif response.status_code == 429:
                print("❌ Rate limited (429) - waiting longer...")
                time.sleep(30)  # Wait 30 seconds for rate limit
                return None
            else:
                print(f"❌ Error: Status code {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
    
    def get_subreddit_posts(self, subreddit, sort_type='hot', limit=5):
        """Get posts from a subreddit with extra safety measures"""
        # Reduce default limit to be more conservative
        limit = min(limit, 10)  # Max 10 posts to be extra safe
        
        valid_sorts = ['hot', 'new', 'top', 'rising']  # Remove controversial as it might be more restricted
        
        if sort_type not in valid_sorts:
            print(f"❌ Invalid sort type. Use: {', '.join(valid_sorts)}")
            return None
        
        # Try the old Reddit URL format first (sometimes works better)
        url = f"https://old.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
        
        print(f"\n🔍 Getting {limit} {sort_type} posts from r/{subreddit}")
        print("=" * 60)
        
        data = self.safe_request(url)
        
        # If old.reddit.com fails, try regular reddit.com
        if not data:
            print("🔄 Trying alternative URL...")
            url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json?limit={limit}"
            data = self.safe_request(url)
        
        if not data:
            return None
        
        # Extract post information
        posts = []
        try:
            for post in data['data']['children']:
                post_data = post['data']
                
                # Convert timestamp to readable date
                created_time = datetime.fromtimestamp(post_data.get('created_utc', 0))
                
                posts.append({
                    'title': post_data.get('title', 'No title'),
                    'author': post_data.get('author', 'Unknown'),
                    'score': post_data.get('score', 0),
                    'num_comments': post_data.get('num_comments', 0),
                    'created_date': created_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'url': post_data.get('url', ''),
                    'selftext': post_data.get('selftext', '')[:300] + '...' if len(post_data.get('selftext', '')) > 300 else post_data.get('selftext', ''),
                    'subreddit': subreddit,
                    'sort_type': sort_type,
                    'permalink': f"https://reddit.com{post_data.get('permalink', '')}"
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
        
        print(f"\n📊 Found {len(posts)} posts:")
        print("=" * 80)
        
        for i, post in enumerate(posts, 1):
            print(f"\n📝 Post {i}: {post['title']}")
            print(f"👤 Author: u/{post['author']}")
            print(f"📊 Score: {post['score']} | 💬 Comments: {post['num_comments']}")
            print(f"📅 Posted: {post['created_date']}")
            
            if post['selftext']:
                print(f"📄 Text: {post['selftext']}")
            
            print(f"🔗 Link: {post['url']}")
            print(f"💬 Reddit: {post['permalink']}")
            print("-" * 80)
    
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
        print(f"📁 You can find this file in: {os.getcwd()}")

def main():
    """Main function with better error handling"""
    collector = EnhancedRedditCollector()
    
    print("🚀 Enhanced Safe Reddit Data Collector v2")
    print("🛡️  Extra protection against blocking")
    print("=" * 50)
    
    # Get user input
    subreddit = input("Enter subreddit name (e.g., 'programming', 'travel'): ").strip()
    
    if not subreddit:
        subreddit = "programming"  # Safe default
        print(f"Using default: {subreddit}")
    
    print("\nAvailable sort types:")
    print("1. hot (most popular currently)")
    print("2. new (newest posts)")
    print("3. top (highest scoring)")
    print("4. rising (gaining popularity)")
    
    sort_choice = input("Choose sort type (1-4, or press Enter for hot): ").strip()
    
    sort_map = {'1': 'hot', '2': 'new', '3': 'top', '4': 'rising'}
    sort_type = sort_map.get(sort_choice, 'hot')
    
    limit = input("How many posts? (1-10, default 5): ").strip()
    try:
        limit = int(limit) if limit else 5
        limit = min(max(limit, 1), 10)  # Keep between 1-10 for safety
    except ValueError:
        limit = 5
    
    print(f"\n🎯 Collecting {limit} {sort_type} posts from r/{subreddit}...")
    print("🛡️  Using enhanced anti-detection methods...")
    
    # Collect the data
    posts = collector.get_subreddit_posts(subreddit, sort_type, limit)
    
    if posts:
        # Display the posts
        collector.display_posts(posts)
        
        # Ask if user wants to save
        save = input("\n💾 Save to CSV file? (y/n): ").strip().lower()
        if save in ['y', 'yes']:
            collector.save_to_file(posts)
            
        print(f"\n✅ Successfully collected {len(posts)} posts!")
    else:
        print("\n❌ No posts collected. Possible reasons:")
        print("   • Subreddit doesn't exist")
        print("   • Reddit is blocking automated requests")
        print("   • Network connection issues")
        print("   • Try again later or use a different subreddit")
    
    print("\n🙏 Thank you for using Enhanced Safe Reddit Collector!")

if __name__ == "__main__":
    main()
