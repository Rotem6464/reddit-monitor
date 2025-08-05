#!/usr/bin/env python3
"""
Reddit Browser Tool
Opens Reddit URLs directly in your browser with exact filtering
No blocking issues since it uses your regular browser
"""

import webbrowser
import time
from datetime import datetime

class RedditBrowserTool:
    def __init__(self):
        # Time filter mapping
        self.time_filters = {
            '1': 'hour',      # Now (last hour)
            '2': 'day',       # Today  
            '3': 'week',      # This Week
            '4': 'month',     # This Month
            '5': 'year',      # This Year
            '6': 'all'        # All Time
        }
        
        # Human-readable time filter names
        self.time_filter_names = {
            'hour': 'Now (Last Hour)',
            'day': 'Today',
            'week': 'This Week', 
            'month': 'This Month',
            'year': 'This Year',
            'all': 'All Time'
        }
        
        # Sort types
        self.sort_types = {
            '1': 'hot',
            '2': 'new', 
            '3': 'top',
            '4': 'rising',
            '5': 'controversial'
        }
        
        self.sort_names = {
            'hot': 'Hot (Most Popular Currently)',
            'new': 'New (Newest Posts)',
            'top': 'Top (Highest Scoring)',
            'rising': 'Rising (Gaining Popularity)', 
            'controversial': 'Controversial (Most Debated)'
        }
    
    def build_reddit_url(self, subreddit, sort_type, time_filter='all'):
        """Build the exact Reddit URL with filters"""
        base_url = f"https://www.reddit.com/r/{subreddit}/{sort_type}/"
        
        # Add time filter parameter for all sort types
        if time_filter != 'all':
            url = f"{base_url}?t={time_filter}"
        else:
            url = base_url
            
        return url
    
    def open_reddit_pages(self, subreddit, sort_type, time_filter, multiple_tabs=False):
        """Open Reddit page(s) in browser"""
        url = self.build_reddit_url(subreddit, sort_type, time_filter)
        
        sort_name = self.sort_names[sort_type]
        time_name = self.time_filter_names[time_filter]
        
        print(f"\n🌐 Opening Reddit in your browser...")
        print(f"📍 Subreddit: r/{subreddit}")
        print(f"📊 Sort: {sort_name}")
        print(f"⏰ Time: {time_name}")
        print(f"🔗 URL: {url}")
        
        # Open in browser
        webbrowser.open(url)
        
        if multiple_tabs:
            print("\n🔄 Opening additional time periods for comparison...")
            time.sleep(2)  # Brief delay between tabs
            
            # Open other useful time periods
            comparison_times = ['day', 'week', 'month'] 
            for comp_time in comparison_times:
                if comp_time != time_filter:
                    comp_url = self.build_reddit_url(subreddit, sort_type, comp_time)
                    comp_name = self.time_filter_names[comp_time]
                    print(f"📱 Opening: {sort_name} - {comp_name}")
                    webbrowser.open(comp_url)
                    time.sleep(1)
        
        return url
    
    def get_user_choices(self):
        """Get user preferences for subreddit and filters"""
        print("🚀 Reddit Browser Tool")
        print("🌐 Opens Reddit directly in your browser - No blocking!")
        print("=" * 60)
        
        # Get subreddit
        subreddit = input("Enter subreddit name (e.g., 'locallama', 'programming'): ").strip()
        if not subreddit:
            subreddit = "programming"
            print(f"Using default: {subreddit}")
        
        # Get sort type
        print("\nChoose sort type:")
        print("1. Hot (Most Popular Currently)")
        print("2. New (Newest Posts)")
        print("3. Top (Highest Scoring)")  
        print("4. Rising (Gaining Popularity)")
        print("5. Controversial (Most Debated)")
        
        sort_choice = input("Choose sort type (1-5, or press Enter for hot): ").strip()
        sort_type = self.sort_types.get(sort_choice, 'hot')
        
        # Get time filter (for ALL sort types)
        print(f"\n⏰ Time filter for '{sort_type}' posts:")
        print("1. Now (Last Hour)")
        print("2. Today") 
        print("3. This Week")
        print("4. This Month")
        print("5. This Year")
        print("6. All Time (default)")
        
        time_choice = input("Choose time filter (1-6, or press Enter for All Time): ").strip()
        time_filter = self.time_filters.get(time_choice, 'all')
        
        # Ask about multiple tabs
        multiple = input("\n📱 Open comparison tabs? (y/n): ").strip().lower()
        multiple_tabs = multiple in ['y', 'yes']
        
        return subreddit, sort_type, time_filter, multiple_tabs
    
    def create_bookmarks(self, subreddit):
        """Generate bookmark URLs for easy access"""
        print(f"\n🔖 Bookmark URLs for r/{subreddit}:")
        print("=" * 50)
        
        bookmark_combinations = [
            ('hot', 'day'),
            ('top', 'week'), 
            ('top', 'month'),
            ('top', 'all'),
            ('new', 'day'),
            ('controversial', 'week')
        ]
        
        for sort_type, time_filter in bookmark_combinations:
            url = self.build_reddit_url(subreddit, sort_type, time_filter)
            sort_name = self.sort_names[sort_type]
            time_name = self.time_filter_names[time_filter]
            print(f"📌 {sort_name} - {time_name}")
            print(f"   {url}")
            print()
    
    def save_urls_to_file(self, subreddit, urls):
        """Save URLs to a text file for later use"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reddit_urls_{subreddit}_{timestamp}.txt"
        
        with open(filename, 'w') as f:
            f.write(f"Reddit URLs for r/{subreddit}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            
            for url_info in urls:
                f.write(f"{url_info['description']}\n")
                f.write(f"{url_info['url']}\n\n")
        
        print(f"💾 URLs saved to: {filename}")

def main():
    """Main function"""
    tool = RedditBrowserTool()
    
    try:
        # Get user choices
        subreddit, sort_type, time_filter, multiple_tabs = tool.get_user_choices()
        
        # Open Reddit in browser
        url = tool.open_reddit_pages(subreddit, sort_type, time_filter, multiple_tabs)
        
        print(f"\n✅ Reddit opened successfully!")
        print(f"🎯 You can now see {tool.sort_names[sort_type]} posts")
        print(f"⏰ Filtered by: {tool.time_filter_names[time_filter]}")
        
        # Ask if user wants bookmarks
        bookmarks = input("\n🔖 Generate bookmark URLs for this subreddit? (y/n): ").strip().lower()
        if bookmarks in ['y', 'yes']:
            tool.create_bookmarks(subreddit)
            
            save_file = input("💾 Save URLs to file? (y/n): ").strip().lower()
            if save_file in ['y', 'yes']:
                # Generate common URL combinations
                urls = []
                for sort_type_key, sort_val in tool.sort_types.items():
                    for time_key, time_val in tool.time_filters.items():
                        url = tool.build_reddit_url(subreddit, sort_val, time_val)
                        description = f"{tool.sort_names[sort_val]} - {tool.time_filter_names[time_val]}"
                        urls.append({'url': url, 'description': description})
                
                tool.save_urls_to_file(subreddit, urls)
        
        print("\n🎉 Success! You now have direct access to Reddit with exact filtering!")
        print("💡 Tip: Bookmark the URLs for quick access later")
        
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
