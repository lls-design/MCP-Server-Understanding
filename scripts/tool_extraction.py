import os
import json
import re
import requests
from typing import List, Dict, Any
import time
from dotenv import load_dotenv




def extract_mcp_servers_from_readme(readme_path: str) -> List[Dict[str, Any]]:
    """
    Extract MCP servers from the README file and categorize them.
    """
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    servers = []
    
    # Split content by sections
    sections = content.split('### ')
    
    for section in sections[1:]:  # Skip the first empty section
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        # Extract category from first line
        category_line = lines[0]
        category_match = re.search(r'<a name="([^"]+)"></a>([^#]+)', category_line)
        if category_match:
            category = category_match.group(2).strip()
        else:
            # Fallback for sections without anchor tags
            category = category_line.split(' ')[0].strip()
        
        # Process each line looking for GitHub links
        for line in lines[1:]:
            line = line.strip()
            if not line.startswith('- '):
                continue
                
            # Extract GitHub URL and name
            github_match = re.search(r'\[([^\]]+)\]\(https://github\.com/([^)]+)\)', line)
            if github_match:
                name = github_match.group(1)
                repo_url = f"https://github.com/{github_match.group(2)}"
                
                # Extract emojis and other metadata
                emojis = re.findall(r'[🎖️🐍📇🏎️🦀#️⃣☕🌊💎☁️🏠📟🍎🪟🐧🎨🧬📂👨‍💻🤖🖥️💬👤🗄️📊🚚🛠️🧮📟📂💰🎮🧠🗺️🎯📊🎥🔎🔒🌐🏃🎧🌎🎧🚆🔄🏢🛠️]', line)
                
                server_info = {
                    "name": name,
                    "repo_url": repo_url,
                    "category": category,
                    "emojis": emojis,
                    "description": line.replace(f'- [{name}]({repo_url})', '').strip()
                }
                servers.append(server_info)
            else:
                print(f"No GitHub URL found in line: {line}")
    return servers


def get_github_stars(repo_url: str, github_token: str = None) -> int:
    """
    Fetch GitHub star count for a repository.
    """
    try:
        # Extract owner and repo from URL
        match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
        if not match:
            return 0
            
        owner, repo = match.groups()
        
        # GitHub API endpoint
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        # Add headers to avoid rate limiting
        headers = {
            'User-Agent': 'MCP-Analyzer/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Add authorization header if token is provided
        if github_token:
            headers['Authorization'] = f'token {github_token}'
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('stargazers_count', 0)
        elif response.status_code == 403:
            # Rate limit exceeded
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', '0')
            rate_limit_reset = response.headers.get('X-RateLimit-Reset', '0')
            print(f"Rate limit exceeded for {repo_url}. Remaining: {rate_limit_remaining}, Reset: {rate_limit_reset}")
            return 0
        else:
            print(f"Failed to fetch stars for {repo_url}: {response.status_code}")
            return 0
            
    except Exception as e:
        print(f"Error fetching stars for {repo_url}: {e}")
        return 0


def main():
    """
    Main function to extract MCP servers and create JSON output.
    """
    load_dotenv('.env')
    readme_path = "Servers/awsome_mcp_list.md"
    output_file = "Servers/mcp_servers_analysis.json"

    if not os.path.exists(output_file):

        print("Extracting MCP servers from README...")
        servers = extract_mcp_servers_from_readme(readme_path)
        
        print(f"Found {len(servers)} MCP servers")
    else:
        with open(output_file, 'r', encoding='utf-8') as f:
            servers = json.load(f)

    # Fetch star counts for each server
    print("Fetching GitHub star counts...")

    github_token = os.getenv('GITHUB_TOKEN')
    if github_token:
        print("Using GitHub token for improved rate limits")
    else:
        print("No GitHub token found, using limited rate (60 requests/hour)")
    
    # Load existing data if available
    
    for i, server in enumerate(servers):
        # Check if we already have stars for this server
        if 'stars' in server and server['stars'] > 0:
            print(f"Skipping {server['name']} (already has {server['stars']} stars)")
            continue
        
        print(f"Processing {i+1}/{len(servers)}: {server['name']}")
        stars = get_github_stars(server['repo_url'], github_token)
        server['stars'] = stars
        
        # Save progress every 10 servers
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(servers, f, indent=2, ensure_ascii=False)
        
        # Add delay based on whether we have a token
        if github_token:
            time.sleep(0.1)  # 10 requests per second with token
        else:
            time.sleep(1)    # 1 request per second without token
    

    
    
    print(f"\nAnalysis complete! Results saved to {output_file}")
    print(f"Total servers analyzed: {len(servers)}")
    
    # Print summary by category
    categories = {}
    for server in servers:
        cat = server['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(server)
    
    print("\nServers by category:")
    for category, servers_in_cat in sorted(categories.items()):
        print(f"  {category}: {len(servers_in_cat)} servers")


if __name__ == '__main__':
    main()
