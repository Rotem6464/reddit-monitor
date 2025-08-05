#!/usr/bin/env python3
"""
Reddit Text Exporter
Helps you manually collect and export Reddit posts to text files
"""

import json
from datetime import datetime
import os

class RedditTextExporter:
    def __init__(self):
        self.posts = []
        self.current_session = {
            'subreddit': '',
            'sort_type': '',
            'time_filter': '',
            'collection_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def start_collection(self):
        """Start a new collection session"""
        print("🚀 Reddit Text Exporter")
        print("📝 Manual Reddit Post Collection Tool")
        print("=" * 50)
        
        # Get session info
        self.current_session['subreddit'] = input("Enter subreddit name (e.g., 'travel'): ").strip()
        
        print("\nSort types:")
        print("1. Hot  2. New  3. Top  4. Rising  5. Controversial")
        sort_choice = input("Sort type (1-5): ").strip()
        sort_map = {'1': 'hot', '2': 'new', '3': 'top', '4': 'rising', '5': 'controversial'}
        self.current_session['sort_type'] = sort_map.get(sort_choice, 'hot')
        
        print("\nTime filters:")
        print("1. Hour  2. Day  3. Week  4. Month  5. Year  6. All Time")
        time_choice = input("Time filter (1-6): ").strip()
        time_map = {'1': 'hour', '2': 'day', '3': 'week', '4': 'month', '5': 'year', '6': 'all'}
        self.current_session['time_filter'] = time_map.get(time_choice, 'all')
        
        reddit_url = self.build_reddit_url()
        
        print(f"\n🎯 Collection Session Started:")
        print(f"📍 Subreddit: r/{self.current_session['subreddit']}")
        print(f"📊 Sort: {self.current_session['sort_type']}")
        print(f"⏰ Time: {self.current_session['time_filter']}")
        print(f"🔗 Reddit URL: {reddit_url}")
        print("\n💡 Instructions:")
        print("1. Open the Reddit URL in your browser")
        print("2. Copy and paste posts using the menu below")
        print("3. Export to text file when done")
        
        self.show_menu()
    
    def build_reddit_url(self):
        """Build Reddit URL for reference"""
        base = f"https://www.reddit.com/r/{self.current_session['subreddit']}/{self.current_session['sort_type']}"
        if self.current_session['time_filter'] != 'all':
            return f"{base}?t={self.current_session['time_filter']}"
        return base
    
    def show_menu(self):
        """Show the main menu"""
        while True:
            print(f"\n📋 Reddit Text Exporter Menu (Posts collected: {len(self.posts)})")
            print("=" * 60)
            print("1. Add a post manually")
            print("2. Add multiple posts (batch mode)")
            print("3. View collected posts")
            print("4. Export to text file")
            print("5. Export to CSV file")
            print("6. Clear all posts")
            print("7. Open Reddit URL in browser")
            print("8. Exit")
            
            choice = input("\nChoose option (1-8): ").strip()
            
            if choice == '1':
                self.add_single_post()
            elif choice == '2':
                self.add_batch_posts()
            elif choice == '3':
                self.view_posts()
            elif choice == '4':
                self.export_to_text()
            elif choice == '5':
                self.export_to_csv()
            elif choice == '6':
                self.clear_posts()
            elif choice == '7':
                self.open_reddit()
            elif choice == '8':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please select 1-8.")
    
    def add_single_post(self):
        """Add a single post manually"""
        print("\n📝 Add New Post")
        print("=" * 30)
        
        post = {
            'position': len(self.posts) + 1,
            'title': input("Post title: ").strip(),
            'author': input("Author (u/username): ").strip(),
            'score': input("Score (upvotes): ").strip(),
            'comments': input("Number of comments: ").strip(),
            'url': input("Post URL (optional): ").strip(),
            'text_content': input("Post text (first few lines, optional): ").strip(),
            'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.posts.append(post)
        print(f"✅ Post #{post['position']} added: {post['title'][:50]}...")
    
    def add_batch_posts(self):
        """Add multiple posts quickly"""
        print("\n📦 Batch Mode - Add Multiple Posts")
        print("=" * 40)
        print("Enter posts one by one. Press Enter on empty title to finish.")
        print("Format: Just enter the title, I'll ask for other details if needed.")
        
        while True:
            title = input(f"\nPost #{len(self.posts) + 1} title (or Enter to finish): ").strip()
            
            if not title:
                break
            
            # Quick mode - just title and basic info
            author = input("  Author (or Enter to skip): ").strip() or "Unknown"
            score = input("  Score (or Enter to skip): ").strip() or "0"
            
            post = {
                'position': len(self.posts) + 1,
                'title': title,
                'author': author,
                'score': score,
                'comments': '0',
                'url': '',
                'text_content': '',
                'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            self.posts.append(post)
            print(f"  ✅ Added: {title[:40]}...")
        
        print(f"\n📦 Batch complete! Added {len([p for p in self.posts if p['collected_at'].startswith(datetime.now().strftime('%Y-%m-%d'))])} posts")
    
    def view_posts(self):
        """View all collected posts"""
        if not self.posts:
            print("\n📭 No posts collected yet.")
            return
        
        print(f"\n📋 Collected Posts ({len(self.posts)} total)")
        print("=" * 80)
        
        for post in self.posts:
            print(f"\n#{post['position']} - {post['title']}")
            print(f"👤 u/{post['author']} | 📊 {post['score']} points | 💬 {post['comments']} comments")
            if post['text_content']:
                print(f"📄 {post['text_content'][:100]}...")
            if post['url']:
                print(f"🔗 {post['url']}")
            print(f"🕒 Collected: {post['collected_at']}")
            print("-" * 60)
    
    def export_to_text(self):
        """Export posts to a formatted text file"""
        if not self.posts:
            print("\n❌ No posts to export.")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reddit_export_{self.current_session['subreddit']}_{self.current_session['sort_type']}_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            # Header
            f.write("Reddit Posts Export\n")
            f.write("=" * 50 + "\n")
            f.write(f"Subreddit: r/{self.current_session['subreddit']}\n")
            f.write(f"Sort: {self.current_session['sort_type']}\n")
            f.write(f"Time Filter: {self.current_session['time_filter']}\n")
            f.write(f"Collection Date: {self.current_session['collection_date']}\n")
            f.write(f"Total Posts: {len(self.posts)}\n")
            f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            
            # Posts
            for post in self.posts:
                f.write(f"POST #{post['position']}\n")
                f.write(f"Title: {post['title']}\n")
                f.write(f"Author: u/{post['author']}\n")
                f.write(f"Score: {post['score']} points\n")
                f.write(f"Comments: {post['comments']}\n")
                
                if post['url']:
                    f.write(f"URL: {post['url']}\n")
                
                if post['text_content']:
                    f.write(f"Text Content:\n{post['text_content']}\n")
                
                f.write(f"Collected: {post['collected_at']}\n")
                f.write("-" * 60 + "\n\n")
        
        print(f"💾 Text export saved: {filename}")
        print(f"📊 Exported {len(self.posts)} posts")
    
    def export_to_csv(self):
        """Export to CSV for spreadsheet analysis"""
        if not self.posts:
            print("\n❌ No posts to export.")
            return
        
        try:
            import pandas as pd
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"reddit_export_{self.current_session['subreddit']}_{self.current_session['sort_type']}_{timestamp}.csv"
            
            # Create DataFrame
            df_data = []
            for post in self.posts:
                df_data.append({
                    'position': post['position'],
                    'title': post['title'],
                    'author': post['author'],
                    'score': post['score'],
                    'comments': post['comments'],
                    'url': post['url'],
                    'text_content': post['text_content'],
                    'subreddit': self.current_session['subreddit'],
                    'sort_type': self.current_session['sort_type'],
                    'time_filter': self.current_session['time_filter'],
                    'collected_at': post['collected_at']
                })
            
            df = pd.DataFrame(df_data)
            df.to_csv(filename, index=False)
            
            print(f"💾 CSV export saved: {filename}")
            print(f"📊 Exported {len(self.posts)} posts")
            print("🔗 You can open this in Excel or Numbers")
            
        except ImportError:
            print("❌ pandas not available for CSV export. Use text export instead.")
    
    def clear_posts(self):
        """Clear all collected posts"""
        if self.posts:
            confirm = input(f"❓ Clear all {len(self.posts)} posts? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                self.posts.clear()
                print("🗑️  All posts cleared.")
        else:
            print("📭 No posts to clear.")
    
    def open_reddit(self):
        """Open Reddit URL in browser"""
        import webbrowser
        url = self.build_reddit_url()
        webbrowser.open(url)
        print(f"🌐 Opened: {url}")

def main():
    """Main function"""
    exporter = RedditTextExporter()
    
    try:
        exporter.start_collection()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
