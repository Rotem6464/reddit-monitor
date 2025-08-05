#!/usr/bin/env python3
"""
Smart Reddit Browser Tool
Handles public/private subreddits and correct URL formatting
"""

import webbrowser
import requests
import time

class SmartRedditBrowser:
    def __init__(self):
        self.time_filters = {
            '1': 'hour',
            '2': 'day', 
            '3': 'week',
            '4': 'month',
            '5': 'year',
            '6': ''  # All time (no parameter)
        }
        
        self.time_names = {
            'hour': 'Now (Last Hour)',
            'day': 'Today',
            'week': 'This Week',
            'month': 'This Month', 
            'year': 'This Year',
            '': 'All Time'
        }
        
        self.sort_types = {
            '1': 'hot',
            '2': 'new',
            '3': 'top', 
            '4': 'rising',
            '5': 'controversial'
        }
    
    def check_subreddit_access(self, subreddit):
        """Check if subreddit is public and accessible"""
        test_url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=1"
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(test_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return True, "✅ Public subreddit - accessible"
            elif response.status_code == 403:
                return False, "🔒 Private subreddit - requires membership"
            elif response.status_code == 404:
                return False, "❌ Subreddit not found"
            else:
                return False, f"❓ Unknown status: {response.status_code}"
                
        except Exception as e:
            return False, f"❌ Error checking: {e}"
    
    def build_reddit_url(self, subreddit, sort_type, time_filter):
        """Build correct Reddit URL"""
        base_url = f"https://www.reddit.com/r/{subreddit}/{sort_type}"
        
        if time_filter:
            return f"{base_url}?t={time_filter}"
        else:
            return base_url
    
    def suggest_alternatives(self, failed_subreddit):
        """Suggest public alternatives to private subreddits"""
        alternatives = {
            'locallama': ['MachineLearning', 'LocalLLaMA_Free', 'ArtificialIntelligence', 'OpenAI'],
            'LocalLLaMA': ['MachineLearning', 'ArtificialIntelligence', 'OpenAI', 'ChatGPT']
        }
        
        return alternatives.get(failed_subreddit.lower(), ['MachineLearning', 'ArtificialIntelligence', 'programming'])

def main():
    browser = SmartRedditBrowser()
    
    print("🧠 Smart Reddit Browser Tool")
    print("🔍 Tests access before opening URLs")
    print("=" * 50)
    
    # Get subreddit
    subreddit = input("Enter subreddit name: ").strip()
    if not subreddit:
        subreddit = "programming"
        print(f"Using default: {subreddit}")
    
    # Test access
    print(f"\n🔍 Testing access to r/{subreddit}...")
    is_accessible, status_msg = browser.check_subreddit_access(subreddit)
    print(status_msg)
    
    if not is_accessible:
        print(f"\n💡 Since r/{subreddit} is not accessible, here are some alternatives:")
        alternatives = browser.suggest_alternatives(subreddit)
        
        for i, alt in enumerate(alternatives, 1):
            print(f"  {i}. r/{alt}")
        
        choice = input(f"\nTry an alternative? (1-{len(alternatives)}, or Enter to continue anyway): ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= len(alternatives):
            subreddit = alternatives[int(choice) - 1]
            print(f"✅ Switched to r/{subreddit}")
            
            # Test the alternative
            is_accessible, status_msg = browser.check_subreddit_access(subreddit)
            print(f"🔍 Testing r/{subreddit}: {status_msg}")
        else:
            print(f"⚠️  Continuing with r/{subreddit} (may require manual navigation)")
    
    # Get sort type
    print(f"\n📊 Sort types for r/{subreddit}:")
    print("1. Hot (Most Popular Currently)")
    print("2. New (Newest Posts)")
    print("3. Top (Highest Scoring)")
    print("4. Rising (Gaining Popularity)")
    print("5. Controversial (Most Debated)")
    
    sort_choice = input("Choose sort (1-5, default hot): ").strip()
    sort_type = browser.sort_types.get(sort_choice, 'hot')
    
    # Get time filter
    print(f"\n⏰ Time filter for {sort_type} posts:")
    print("1. Now (Last Hour)")
    print("2. Today")
    print("3. This Week") 
    print("4. This Month")
    print("5. This Year")
    print("6. All Time (default)")
    
    time_choice = input("Choose time (1-6, default All Time): ").strip()
    time_filter = browser.time_filters.get(time_choice, '')
    
    # Build and display URL
    url = browser.build_reddit_url(subreddit, sort_type, time_filter)
    time_name = browser.time_names[time_filter]
    
    print(f"\n🎯 Final URL:")
    print(f"📍 Subreddit: r/{subreddit}")
    print(f"📊 Sort: {sort_type}")
    print(f"⏰ Time: {time_name}")
    print(f"🔗 URL: {url}")
    
    # Open URL
    open_choice = input(f"\n🌐 Open in browser? (y/n): ").strip().lower()
    if open_choice in ['y', 'yes', '']:
        webbrowser.open(url)
        print("✅ Opened in browser!")
        
        if not is_accessible:
            print("\n💡 Manual steps if the direct URL doesn't work:")
            print(f"1. Go to: https://www.reddit.com/r/{subreddit}")
            print(f"2. Click on '{sort_type.title()}' tab")
            if time_filter:
                print(f"3. Look for time filter options and select '{time_name}'")
            print("4. Or modify the URL manually by adding the sort and time parameters")
    
    # Offer to create bookmarks
    bookmark_choice = input(f"\n🔖 Create bookmark file for r/{subreddit}? (y/n): ").strip().lower()
    if bookmark_choice in ['y', 'yes']:
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reddit_bookmarks_{subreddit}_{timestamp}.txt"
        
        with open(filename, 'w') as f:
            f.write(f"Reddit Bookmarks for r/{subreddit}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            if not is_accessible:
                f.write("⚠️  NOTE: This is a private subreddit. URLs may not work directly.\n")
                f.write(f"Manual access: https://www.reddit.com/r/{subreddit}\n\n")
            
            for sort_name, sort_val in browser.sort_types.items():
                for time_name, time_val in browser.time_filters.items():
                    url = browser.build_reddit_url(subreddit, sort_val, time_val)
                    time_desc = browser.time_names[time_val]
                    f.write(f"{sort_val.title()} - {time_desc}\n")
                    f.write(f"{url}\n\n")
        
        print(f"💾 Bookmarks saved to: {filename}")
    
    print("\n🎉 Done! Happy Reddit browsing!")

if __name__ == "__main__":
    main()
