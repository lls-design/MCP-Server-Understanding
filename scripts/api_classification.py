#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API classification script.
Samples APIs from api_cache_external.json, classifies them with an LLM, and merges similar categories.
"""

import json
import random
import os
import sys
from collections import defaultdict
from typing import List, Dict, Tuple, Any, Optional
import time
import dotenv

# Add the project root to the Python path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables.
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from utils.llm_call import get_openai_client, generate_content_openai


def load_api_data(json_path: str) -> List[Dict]:
    """
    Load all API data from a JSON file.
    
    Args:
        json_path: JSON file path.
        
    Returns:
        API list, where each item contains api_name and description.
    """
    print(f"Loading API data from: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    api_list = []
    for language in data:
        for api_name, api_info in data[language].items():
            if api_info.get('external_api', False) and 'external_api_summary' in api_info:
                api_list.append({
                    'api_name': api_name,
                    'description': api_info['external_api_summary'],
                    'url': api_info.get('external_api_url', ''),
                    'language': language
                })
    
    print(f"Loaded {len(api_list)} APIs")
    return api_list


def sample_apis(api_list: List[Dict], min_count: int = 50, max_count: int = 100) -> List[Dict]:
    """
    Randomly sample APIs.
    
    Args:
        api_list: Full API list.
        min_count: Minimum sample size.
        max_count: Maximum sample size.
        
    Returns:
        Sampled API list.
    """
    sample_size = random.randint(min_count, max_count)
    sample_size = min(sample_size, len(api_list))
    sampled = random.sample(api_list, sample_size)
    return sampled


def classify_apis_with_llm(client, apis: List[Dict]) -> List[Dict]:
    """
    Classify APIs with an LLM.
    
    Args:
        client: OpenAI client.
        apis: API list.
        
    Returns:
        Classification results, where each item contains category_name and category_definition.
    """
    # Build the prompt.
    api_descriptions = []
    for i, api in enumerate(apis, 1):
        url_info = f" (URL: {api['url']})" if api.get('url') else ""
        api_descriptions.append(f"{i}. {api['api_name']}: {api['description']}{url_info}")
    
    prompt = f"""You are performing semantic analysis and classification of external APIs for permission analysis research. These APIs are extracted from real-world codebases and will be used for security and permission boundary analysis in academic research published at top-tier conferences like ISSTA.

API List:
{chr(10).join(api_descriptions)}

**CRITICAL: ABSOLUTELY FORBIDDEN WORDS IN CATEGORY NAMES**

The following words are STRICTLY PROHIBITED and MUST NEVER appear in any category name:
- "Specialized" / "Specialized Domain" / "Specialized Services" / "Specialized Data"
- "External" / "External Service" / "External API" / "External HTTP"
- "Generic" / "General" / "Generic Services"
- "Domain Services" / "Domain Data Services"
- "Integration Services" / "Integration" (when used alone)
- "Platform Services" / "Platform" (when used alone)
- "Data Services" (without specific domain prefix)

If you use any of these words, your classification will be REJECTED. You MUST split or rename categories to avoid these words.

**Classification Requirements:**

1. **Single Permission Domain Per Category**: Each category MUST focus on ONE specific permission domain. DO NOT mix different permission domains in a single category.
   - BAD: "Social and Decentralized Identity Platforms" (mixes social media with identity management)
   - BAD: "Application Integration and Messaging" (too generic, mixes multiple domains)
   - BAD: "Specialized Domain Data Services" (FORBIDDEN word "Specialized", mixes healthcare, financial, weather APIs)
   - BAD: "Specialized Research and Academic Data Services" (FORBIDDEN word "Specialized", mixes academic, chemical, media APIs)
   - BAD: "External HTTP Integration Services" (FORBIDDEN word "External", too generic)
   - BAD: "Specialized Analytics and Monitoring Services" (FORBIDDEN word "Specialized")
   - BAD: "Specialized AI and Machine Learning Services" (FORBIDDEN word "Specialized")
   - BAD: "Communication and Messaging Services" (mixes SMS, Telegram, Email - MUST split)
   - BAD: "Application Lifecycle and Content Management" (mixes Obsidian, Notion, DaVinci Resolve, Gmail, GitLab - MUST split)
   - BAD: "Communication Platform Services" (mixes WhatsApp instant messaging, Twitter/X social media, email services - MUST split into "Instant Messaging Services", "Social Media Management", "Email Services")
   - BAD: "Media and Content Management" (mixes Plex media server, GIMP image editing, ZIM file operations - MUST split into "Media Server Management", "Image Editing Services", "File System Operations")
   - BAD: "Version Control and Development Tools" (mixes git version control, Ambari cluster management, txtai NLP - MUST split into "Code Repository Services", "Cluster Management Services", "NLP and Text Processing Services")
   - BAD: "Media Production Services" (mixes DaVinci Resolve video editing, GeoServer geographic services, DiagramIconsResponse icon services - MUST split into "Video Production Services", "Geographic Information Services", "Icon and Design Services")
   - GOOD: "Social Media Management" (single domain: social media platforms)
   - GOOD: "Identity and Access Management" (single domain: authentication/authorization)
   - GOOD: "Healthcare Data Services" (single domain: healthcare/medical APIs)
   - GOOD: "Email Services" (single domain: email APIs)
   - GOOD: "SMS and Telephony Services" (single domain: SMS/telephony APIs)
   - GOOD: "Academic Research Data Services" (single domain: academic APIs)

2. **Service-Specific Classification - STRICTLY ENFORCED**: 
   - ABSOLUTELY FORBIDDEN generic categories: "external service", "third-party API", "SaaS integration", "external platform", "Specialized Domain Services", "Specialized Domain Data Services" (EXCEPT when used for HTTP client APIs), "Specialized Research and Academic Data Services", "Specialized Analytics and Monitoring Services", "Specialized AI and Machine Learning Services", "External HTTP Integration Services", "Application Integration", "Domain Services", "System-Level Operations", "System Operations", "Data Services", "Platform Services", "Integration Services"
   - Instead, classify based on the SPECIFIC service provider type or functional domain
   - If you encounter APIs from different specialized domains, you MUST split them into separate categories:
     * Healthcare LOINC, medical terminology → "Healthcare Terminology Services" (NOT "Specialized Domain Data Services")
     * Financial Baostock, market data → "Financial Market Data Services" (NOT "Specialized Domain Data Services")
     * Weather/climate APIs → "Weather and Climate Services" (NOT "Specialized Domain Data Services")
     * Academic OpenAlex → "Academic Research Data Services" (NOT "Specialized Research and Academic Data Services")
     * Chemical ChEMBL → "Chemical and Biomedical Data Services" (NOT "Specialized Research and Academic Data Services")
     * Media Shotgun → "Media Production Tracking Services" (NOT "Specialized Research and Academic Data Services")
   - Examples of GOOD categories: 
     * "Social Media Management" (for Twitter/X, Facebook, Instagram, Bluesky APIs)
     * "Cloud Storage Services" (for AWS S3, Google Cloud Storage, Azure Blob APIs)
     * "Payment Processing" (for Stripe, PayPal, Square APIs)
     * "Blockchain and Cryptocurrency Services" (for Ethereum, Solana, Bitcoin APIs)
     * "Database Management" (for PostgreSQL, MySQL, MongoDB APIs)
     * "File System Operations" (for local file system APIs)
     * "System Command Execution" (for shell command, subprocess APIs)
     * "Specialized Domain Data Services" (for generic HTTP clients like axios, requests - NOT "External HTTP Integration Services")
     * "AI and Machine Learning Services" (for AI/ML APIs - NOT "Specialized AI and Machine Learning Services")
   - Examples of BAD categories: 
     * "External Service", "Third-Party Integration", "External API"
     * "Specialized Domain Services" (FORBIDDEN word "Specialized", MUST split)
     * Note: "Specialized Domain Data Services" is ALLOWED ONLY for HTTP client APIs (axios, requests, httpx, urllib, fetch)
     * "Specialized Research and Academic Data Services" (FORBIDDEN word "Specialized", MUST split)
     * "External HTTP Integration Services" (FORBIDDEN word "External", use "Specialized Domain Data Services")
     * "Specialized Analytics and Monitoring Services" (FORBIDDEN word "Specialized", use "Analytics and Monitoring Services")
     * "Specialized AI and Machine Learning Services" (FORBIDDEN word "Specialized", use "AI and Machine Learning Services")
     * "System-Level Operations" (too broad, use "System Command Execution")
     * "Application Integration and Messaging" (too broad, mixes domains, MUST split)
     * "Communication and Messaging Services" (mixes SMS, Telegram, Email - MUST split into "SMS and Telephony Services", "Instant Messaging Services", "Email Services")
     * "Communication Platform Services" (mixes WhatsApp instant messaging, Twitter/X social media, email services - MUST split into "Instant Messaging Services", "Social Media Management", "Email Services")
     * "Application Lifecycle and Content Management" (mixes multiple app types - MUST split)
     * "Media and Content Management" (mixes Plex media server, GIMP image editing, ZIM file operations - MUST split into "Media Server Management", "Image Editing Services", "File System Operations")
     * "Version Control and Development Tools" (mixes git version control, Ambari cluster management, txtai NLP - MUST split into "Code Repository Services", "Cluster Management Services", "NLP and Text Processing Services")
     * "Media Production Services" (mixes DaVinci Resolve video editing, GeoServer geographic services, DiagramIconsResponse icon services - MUST split into "Video Production Services", "Geographic Information Services", "Icon and Design Services")

3. **Standardized Category Naming Template**: Use consistent naming patterns to ensure reproducibility:
   - Pattern 1: "[Service Type] Management" (e.g., "Social Media Management", "Cloud Infrastructure Management")
   - Pattern 2: "[Service Type] Services" (e.g., "Cloud Storage Services", "Payment Processing Services")
   - Pattern 3: "[Domain] Operations" (e.g., "Database Operations", "File System Operations")
   - Pattern 4: "[Function] and [Related Function]" (e.g., "Identity and Access Management", "Blockchain and Cryptocurrency Services")
   
   **Standardized Names for Common Categories** (use these exact names when applicable):
   - Social media APIs → "Social Media Management" (NOT "Social Media and Content Platforms", NOT "Social Media Services")
   - Database APIs → "Database Management" (NOT "Database Operations", NOT "Database and Data Store Operations")
   - Identity/auth APIs → "Identity and Access Management" (NOT "Authentication and Credential Management", NOT "Authentication Management")
   - File system APIs → "File System Operations" (NOT "File System and Local Resource Operations", NOT "File System and Storage Operations")
   - Cloud infrastructure APIs → "Cloud Infrastructure Management" (consistent across all rounds)
   - Blockchain APIs → "Blockchain and Cryptocurrency Services" (consistent across all rounds)
   - Browser automation APIs → "Browser Automation and Web Interaction" (consistent name)
   - System command APIs → "System Command Execution" (NOT "System-Level Operations", NOT "System Process and Resource Monitoring")
   - HTTP client APIs → "Specialized Domain Data Services" (NOT "External HTTP Integration Services", NOT "HTTP Integration Services")
   - AI/ML APIs → "AI and Machine Learning Services" (NOT "Specialized AI and Machine Learning Services")
   - Analytics/monitoring APIs → "Analytics and Monitoring Services" (NOT "Specialized Analytics and Monitoring Services")
   - Financial trading APIs → "Financial Trading Services" (NOT "Financial Services and Trading")
   - Financial market data APIs → "Financial Market Data Services" (consistent name)
   - Payment APIs → "Payment Processing" (consistent name)

4. **Financial Services Naming Standardization** (CRITICAL):
   - Trading platforms (Robinhood, Bybit, trading execution) → "Financial Trading Services" (NOT "Financial Services and Trading")
   - Market data providers (Baostock, Futu OpenAPI for data) → "Financial Market Data Services" (consistent name)
   - Payment processors (Stripe, PayPal, Square) → "Payment Processing" (consistent name)
   - Use these standardized names consistently across all rounds

5. **Consistent Granularity**: All categories should have similar granularity levels:
   - If you have "Social Media Management", you should also have "Cloud Infrastructure Management" (not "Cloud Services" which is too broad)
   - If you have "Database Management", you should also have "File System Operations" (not "System Operations" which is too broad)
   - Avoid categories that are significantly broader or narrower than others
   - If a category seems too broad (e.g., "Enterprise Application and Project Management"), split it into:
     * "Project Management Services" (for project tracking tools)
     * "Code Repository Services" (for version control systems)
   - If a category mixes multiple service types (e.g., "Communication and Messaging Services"), split it into:
     * "SMS and Telephony Services" (for Twilio SMS)
     * "Instant Messaging Services" (for Telegram)
     * "Email Services" (for Resend, Gmail)
   - If a category mixes multiple application types (e.g., "Application Lifecycle and Content Management"), split it into:
     * "Content Management Services" (for Obsidian, Notion)
     * "Media Production Services" (for DaVinci Resolve)
     * "Email Services" (for Gmail)
     * "Code Repository Services" (for GitLab)

6. **Granular Permission Boundaries**: Each category must represent APIs that:
   - Require similar permission scopes (e.g., all require OAuth with similar scopes)
   - Access similar types of sensitive resources (e.g., all access user financial data)
   - Pose similar security risks (e.g., all risk financial loss)
   - Share common authentication/authorization patterns (e.g., all use API keys vs all use OAuth)

7. **Strict Mutual Exclusivity**: Categories must be clearly distinct with non-overlapping boundaries:
   - If an API could belong to multiple categories, your classification is wrong
   - Use clear distinguishing criteria in category definitions
   - Examples of overlapping (BAD):
     * "Authentication and Identity Management" vs "Authentication and Credential Management" (too similar, use "Identity and Access Management")
     * "Database Operations" vs "Database and Data Store Operations" (essentially the same, use "Database Management")
     * "File System Operations" vs "File System and Local Resource Operations" (same, use "File System Operations")
   - If two categories seem similar, merge them using the standardized name

8. **Academic Rigor for ISSTA**: Categories must be:
   - Precise enough for reproducible security research analysis
   - Specific enough to enable meaningful permission boundary identification
   - Well-defined with clear, measurable characteristics
   - Stable across different API samples (use standardized names, avoid ad-hoc categories)

**Mandatory Classification Rules:**

Rule 1: **Service Provider-Based Classification**
- If APIs call Twitter/X, Facebook, Instagram, Bluesky → "Social Media Management" (standardized name)
- If APIs call AWS S3, GCS, Azure Blob → "Cloud Storage Services"
- If APIs call Stripe, PayPal, Square → "Payment Processing" (standardized name)
- If APIs call Robinhood, Bybit (trading execution) → "Financial Trading Services" (NOT "Financial Services and Trading")
- If APIs call Baostock, Futu OpenAPI (market data) → "Financial Market Data Services" (standardized name)
- If APIs call GitHub, GitLab, Bitbucket → "Code Repository Services" or "Version Control Services"
- If APIs call AWS EC2, Azure VMs, GCP Compute → "Cloud Infrastructure Management" (standardized name)
- If APIs call PostgreSQL, MySQL, MongoDB → "Database Management" (standardized name)
- If APIs call Ethereum, Solana, Bitcoin networks → "Blockchain and Cryptocurrency Services" (standardized name)
- If APIs call LOINC, medical terminology services → "Healthcare Terminology Services" (NOT "Specialized Domain Data Services")
- If APIs call Baostock, financial market data → "Financial Market Data Services" (NOT "Specialized Domain Data Services")
- If APIs call weather/climate services → "Weather and Climate Services" (NOT "Specialized Domain Data Services")
- If APIs call OpenAlex, academic research → "Academic Research Data Services" (NOT "Specialized Research and Academic Data Services")
- If APIs call ChEMBL, chemical data → "Chemical and Biomedical Data Services" (NOT "Specialized Research and Academic Data Services")
- If APIs call axios, requests, generic HTTP clients → "Specialized Domain Data Services" (NOT "External HTTP Integration Services")
- If APIs call OpenAI, MLflow, AI services → "AI and Machine Learning Services" (NOT "Specialized AI and Machine Learning Services")

Rule 2: **Permission Scope-Based Classification**
- If APIs require file system access → "File System Operations" (standardized name, NOT "File System and Local Resource Operations")
- If APIs require database credentials → "Database Management" (standardized name, NOT "Database Operations")
- If APIs require OAuth with social scopes → "Social Media Management" (standardized name)
- If APIs require cloud IAM roles → "Cloud Infrastructure Management" (standardized name)
- If APIs execute shell commands/subprocesses → "System Command Execution" (NOT "System-Level Operations")

Rule 3: **Prohibited Category Patterns** (ABSOLUTELY FORBIDDEN):
- ❌ ANY category name containing "Specialized" EXCEPT "Specialized Domain Data Services" for HTTP client APIs (e.g., "Specialized Domain Services", "Specialized Research and Academic Data Services", "Specialized Analytics and Monitoring Services", "Specialized AI and Machine Learning Services" are FORBIDDEN)
- ✅ "Specialized Domain Data Services" is ALLOWED ONLY for generic HTTP client APIs (axios, requests, httpx, urllib, fetch)
- ❌ ANY category name containing "External" (e.g., "External Service", "External HTTP Integration Services", "External API")
- ❌ "System-Level Operations" (too broad, use "System Command Execution" or "OS Process Management")
- ❌ "System Operations" (too broad, be more specific)
- ❌ "Application Integration and Messaging" (too broad, split by specific service type)
- ❌ "Communication and Messaging Services" (mixes SMS, Telegram, Email - MUST split)
- ❌ "Communication Platform Services" (mixes WhatsApp instant messaging, Twitter/X social media, email services - MUST split into "Instant Messaging Services", "Social Media Management", "Email Services")
- ❌ "Application Lifecycle and Content Management" (mixes multiple app types - MUST split)
- ❌ "Media and Content Management" (mixes Plex media server, GIMP image editing, ZIM file operations - MUST split into "Media Server Management", "Image Editing Services", "File System Operations")
- ❌ "Version Control and Development Tools" (mixes git version control, Ambari cluster management, txtai NLP - MUST split into "Code Repository Services", "Cluster Management Services", "NLP and Text Processing Services")
- ❌ "Media Production Services" (mixes DaVinci Resolve video editing, GeoServer geographic services, DiagramIconsResponse icon services - MUST split into "Video Production Services", "Geographic Information Services", "Icon and Design Services")
- ❌ "Enterprise Service and IT Management" (too broad, split into specific services)
- ❌ "Domain Services" or "Specialized Services" (too vague)
- ❌ "Data Services" (too generic, specify the type)
- ❌ Categories that mix multiple permission domains (e.g., "Social and Identity")
- ❌ Categories that mix communication platforms (e.g., "Communication Platform Services" mixing instant messaging, social media, email)
- ❌ Categories that mix media types (e.g., "Media and Content Management" mixing media servers, image editing, file operations)
- ❌ Categories that mix development tools (e.g., "Version Control and Development Tools" mixing version control, cluster management, NLP)

Rule 4: **Category Naming Consistency** (CRITICAL):
- ALWAYS use standardized names from the list above when applicable
- Use consistent naming patterns: "[Service Type] Management" or "[Service Type] Services" or "[Domain] Operations"
- Examples: "Social Media Management", "Cloud Storage Services", "Database Management", "File System Operations"
- Avoid variations: "Social Media and Content Platforms" → use "Social Media Management"
- Avoid variations: "Database and Data Store Operations" → use "Database Management"
- Avoid variations: "File System and Local Resource Operations" → use "File System Operations"
- Avoid variations: "Authentication and Credential Management" → use "Identity and Access Management"
- Avoid variations: "Financial Services and Trading" → use "Financial Trading Services"
- Avoid variations: "External HTTP Integration Services" → use "Specialized Domain Data Services"
- Avoid variations: "Specialized AI and Machine Learning Services" → use "AI and Machine Learning Services"

**Classification Process:**

Step 1: Identify all unique service domains in the API list
Step 2: Group APIs by service provider type or permission scope
Step 3: For each group, assign a standardized category name (use the standardized names above)
Step 4: If you encounter APIs that don't fit existing categories, create new ones following the naming patterns
Step 5: **CRITICAL CHECK**: Verify NO category name contains forbidden words ("Specialized", "External", "Generic", "Domain Services", "Integration Services", "Platform Services", "Data Services")
Step 6: **CRITICAL CHECK**: If a category mixes multiple service types, SPLIT it into separate categories
Step 7: Ensure all categories use consistent naming (check against standardized names)
Step 8: Split any category that seems too broad or mixes domains

Please classify these APIs into exactly 10 categories. Each category must include:

1. **category_name**: A specific, descriptive name following the standardized naming patterns above. The name must:
   - Use standardized names when applicable (e.g., "Social Media Management", "Database Management")
   - Identify a single, specific service domain or permission scope
   - Be consistent with other category names in granularity
   - NOT be a generic term or mix multiple domains
   - NOT contain ANY forbidden words: "Specialized" (EXCEPT "Specialized Domain Data Services" for HTTP clients), "External", "Generic", "Domain Services", "Integration Services", "Platform Services", "Data Services"
   - NOT use prohibited patterns like "Specialized Domain Services" or "System-Level Operations" or "External HTTP Integration Services"
   - Examples: "Social Media Management", "Cloud Storage Services", "Database Management", "File System Operations", "Specialized Domain Data Services", "AI and Machine Learning Services"
   - Counter-examples: "External Service", "System-Level Operations", "Application Integration", "External HTTP Integration Services", "Specialized AI and Machine Learning Services" (Note: "Specialized Domain Data Services" is now ALLOWED for HTTP clients)

2. **category_definition**: A detailed definition that explicitly describes:
   - The SPECIFIC service providers/platforms included (e.g., "Twitter, Facebook, Instagram" not "social platforms")
   - The permission scopes required (e.g., "OAuth tokens with read/write social media scopes")
   - The security implications and sensitive resources accessed (e.g., "user social media content, posting capabilities")
   - The distinguishing characteristics that separate this category from others (e.g., "distinguished from identity management by focus on social content rather than authentication")
   - Why this category is distinct from similar categories (e.g., "different from 'Identity and Access Management' which handles authentication tokens, not social content")

Return the result in JSON format:
{{
    "categories": [
        {{
            "category_name": "Standardized Category Name (e.g., Social Media Management, Database Management, Specialized Domain Data Services, NOT External HTTP Integration Services, NOT Specialized AI and Machine Learning Services)",
            "category_definition": "Detailed definition with: (1) specific service providers, (2) exact permission scopes, (3) security implications, (4) clear distinguishing characteristics from other categories"
        }},
        ...
    ]
}}

**Final Validation Checklist** (verify before returning - ALL must be checked):
- [ ] All 10 categories are created
- [ ] NO category name contains forbidden words: "Specialized" (EXCEPT "Specialized Domain Data Services" for HTTP clients), "External", "Generic", "Domain Services", "Integration Services", "Platform Services", "Data Services"
- [ ] NO category uses prohibited patterns: "Specialized Domain Services", "Specialized Domain Data Services" (EXCEPT when used for HTTP client APIs), "Specialized Research and Academic Data Services", "Specialized Analytics and Monitoring Services", "Specialized AI and Machine Learning Services", "External HTTP Integration Services", "System-Level Operations"
- [ ] Each category focuses on a single permission domain (no mixing)
- [ ] Categories use standardized names when applicable (check against the standardized name list)
- [ ] Financial services use standardized names: "Financial Trading Services", "Financial Market Data Services", "Payment Processing"
- [ ] Categories have consistent granularity (none significantly broader/narrower)
- [ ] Categories are mutually exclusive (no overlap)
- [ ] Category names follow consistent naming patterns
- [ ] Each definition includes specific service providers, not generic descriptions
- [ ] Each definition clearly distinguishes the category from similar ones
- [ ] No category mixes different specialized domains (e.g., healthcare + financial + weather, SMS + Telegram + Email, Obsidian + Notion + DaVinci + Gmail + GitLab)

**Critical Constraints:**
- Category names MUST use standardized names when applicable (e.g., "Social Media Management", "Database Management", "File System Operations", "Specialized Domain Data Services", "AI and Machine Learning Services")
- NEVER use forbidden words: "Specialized" (EXCEPT "Specialized Domain Data Services" for HTTP clients), "External", "Generic", "Domain Services", "Integration Services", "Platform Services", "Data Services"
- NEVER use generic terms like "external service", "third-party API", "SaaS integration", "external platform", "Specialized Domain Services", "Specialized Domain Data Services" (EXCEPT when used for HTTP client APIs), "Specialized Research and Academic Data Services", "Specialized Analytics and Monitoring Services", "Specialized AI and Machine Learning Services", "External HTTP Integration Services", "Application Integration", "Domain Services", "System-Level Operations", "System Operations"
- Categories MUST be mutually exclusive with clear, non-overlapping boundaries
- Each category MUST represent a distinct permission boundary meaningful for security research
- Categories MUST NOT mix different permission domains
- If encountering multiple specialized domains, SPLIT them into separate categories
- If encountering mixed service types (e.g., SMS + Telegram + Email), SPLIT them into separate categories
- Return valid JSON format only
"""
    
    print(f"Calling LLM for classification, API count: {len(apis)}")
    result = generate_content_openai(
        client=client,
        prompt=prompt,
        model='qwen3-max-preview',  # Use qwen3-max-preview, a model already validated in this project.
        repeat=10,
        output_check={'categories': []}
    )
    
    if result is None:
        print("Warning: LLM call failed, returning empty classification")
        return []
    
    categories = result.get('categories', [])
    print(f"Classification completed, got {len(categories)} categories")
    return categories


def merge_similar_categories(all_categories: List[List[Dict]]) -> Dict[str, Dict]:
    """
    Merge semantically identical or highly similar categories.
    
    Args:
        all_categories: Classification results from all rounds.
        
    Returns:
        Merged category dictionary keyed by category name, with definitions and frequencies as values.
    """
    print("Merging similar categories...")
    
    # First count the frequency of each category.
    category_freq: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'definitions': [], 'count': 0})
    
    for round_categories in all_categories:
        for category in round_categories:
            name = category.get('category_name', '').strip()
            definition = category.get('category_definition', '').strip()
            
            if name:
                category_freq[name]['definitions'].append(definition)
                category_freq[name]['count'] += 1
    
    # Use the LLM to judge category similarity and merge categories.
    client = get_openai_client()
    merged_categories = {}
    processed_names = set()
    
    category_list = list(category_freq.items())
    
    for i, (name1, info1) in enumerate(category_list):
        if name1 in processed_names:
            continue
        
        # Find similar categories.
        similar_categories = [name1]
        info1_definitions: List[str] = info1.get('definitions', [])
        info1_count: int = info1.get('count', 0)
        representative_definition = info1_definitions[0] if info1_definitions else ""
        
        for j, (name2, info2) in enumerate(category_list[i+1:], start=i+1):
            if name2 in processed_names:
                continue
            
            # Use the LLM to judge whether categories are similar.
            info2_definitions: List[str] = info2.get('definitions', [])
            if are_categories_similar(client, name1, info1_definitions[0] if info1_definitions else "", 
                                     name2, info2_definitions[0] if info2_definitions else ""):
                similar_categories.append(name2)
                processed_names.add(name2)
                # Merge frequencies.
                info1_count += info2.get('count', 0)
                info1_definitions.extend(info2_definitions)
        
        # Select the most frequent definition as the representative definition.
        if info1_definitions:
            # Use the longest definition as the representative.
            representative_definition = max(set(info1_definitions), key=len)
        
        merged_categories[name1] = {
            'category_name': name1,
            'category_definition': representative_definition,
            'frequency': info1_count,
            'merged_from': similar_categories if len(similar_categories) > 1 else []
        }
        
        processed_names.add(name1)
    
    print(f"Merging completed, merged from {len(category_freq)} categories to {len(merged_categories)} categories")
    return merged_categories


def are_categories_similar(client, name1: str, def1: str, name2: str, def2: str) -> bool:
    """
    Use the LLM to determine whether two categories are similar.
    
    Args:
        client: OpenAI client.
        name1: Category 1 name.
        def1: Category 1 definition.
        name2: Category 2 name.
        def2: Category 2 definition.
        
    Returns:
        Whether the categories are similar.
    """
    prompt = f"""Please determine whether the following two API categories are semantically identical or highly similar.

Category 1:
Name: {name1}
Definition: {def1}

Category 2:
Name: {name2}
Definition: {def2}

Please determine whether these two categories represent the same or highly similar concept. If similar, return true; otherwise return false.

Please return in JSON format:
{{
    "similar": true or false
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={'similar': False}
        )
        
        if result:
            return result.get('similar', False)
    except Exception as e:
        print(f"Error judging category similarity: {e}")
    
    return False


def merge_categories_for_permission_analysis(client, all_categories: List[List[Dict]], target_count: int = 10) -> Dict[str, Dict]:
    """
    Merge categories for permission analysis so the final categories fit permission analysis needs.
    
    The merging strategy considers:
    1. Permission-domain similarity (read/write/execute)
    2. Resource-type similarity (local/remote/cloud)
    3. Security risk-level similarity
    4. Authentication-method similarity
    5. **Permission-domain consistency** (core requirement)
    
    Args:
        client: OpenAI client.
        all_categories: Classification results from all rounds.
        target_count: Target number of categories (default: 10).
        
    Returns:
        Merged category dictionary keyed by category name, with definitions and frequencies as values.
    """
    print(f"Merging categories for permission analysis, target count: {target_count}")
    
    # First count the frequency of each category.
    category_freq: Dict[str, Dict[str, Any]] = defaultdict(lambda: {'definitions': [], 'count': 0})
    
    for round_categories in all_categories:
        for category in round_categories:
            name = category.get('category_name', '').strip()
            definition = category.get('category_definition', '').strip()
            
            if name:
                category_freq[name]['definitions'].append(definition)
                category_freq[name]['count'] += 1
    
    print(f"Found {len(category_freq)} unique categories before merging")
    
    if len(category_freq) == 0:
        print("Warning: No categories found to merge")
        return {}
    
    if len(category_freq) <= target_count:
        print(f"Category count ({len(category_freq)}) is already <= target ({target_count}), returning as-is")
        result = {}
        for name, info in category_freq.items():
            result[name] = {
                'category_name': name,
                'category_definition': info['definitions'][0] if info['definitions'] else "",
                'frequency': info['count'],
                'merged_from': []
            }
        return result
    
    # Use the LLM to merge categories for permission analysis.
    # First let the LLM analyze permission features for each category.
    print("Analyzing permission features for each category...")
    category_permission_features = {}
    for idx, (name, info) in enumerate(category_freq.items(), 1):
        definition = info['definitions'][0] if info['definitions'] else ""
        print(f"  Analyzing [{idx}/{len(category_freq)}]: {name}")
        features = analyze_permission_features(client, name, definition)
        category_permission_features[name] = features
    
    # Cluster and merge based on permission features.
    merged_categories = {}
    processed_names = set()
    category_list = list(category_freq.items())
    
    # Phase 1: strictly merge similar categories without forcing the target count.
    print("Phase 1: Strictly merging similar categories (permission domain must match)...")
    while len(processed_names) < len(category_list):
        # Find the most frequent unprocessed category as the seed.
        seed_candidates = [(name, info) for name, info in category_list 
                          if name not in processed_names]
        if not seed_candidates:
            break
            
        # Select the highest-frequency category as the seed.
        seed_name, seed_info = max(seed_candidates, key=lambda x: x[1]['count'])
        
        # Find categories that can be merged into the seed with strict permission-domain matching.
        merge_group = [seed_name]
        seed_features = category_permission_features.get(seed_name, {})
        seed_definitions = seed_info['definitions']
        total_count = seed_info['count']
        
        # Only merge categories with highly consistent permission domains; do not force the target count.
        for other_name, other_info in category_list:
            if other_name in processed_names or other_name == seed_name:
                continue
            
            # Strictly check whether categories can be merged; permission domains must match.
            other_features = category_permission_features.get(other_name, {})
            if can_merge_for_permission_analysis(
                client, seed_name, seed_info['definitions'][0] if seed_info['definitions'] else "",
                other_name, other_info['definitions'][0] if other_info['definitions'] else "",
                seed_features, other_features
            ):
                merge_group.append(other_name)
                processed_names.add(other_name)
                total_count += other_info['count']
                seed_definitions.extend(other_info['definitions'])
        
        # Generate the merged category name and definition.
        merged_name, merged_definition = generate_merged_category(
            client, merge_group, seed_definitions, seed_name, seed_info['definitions'][0] if seed_info['definitions'] else ""
        )
        
        merged_categories[merged_name] = {
            'category_name': merged_name,
            'category_definition': merged_definition,
            'frequency': total_count,
            'merged_from': merge_group if len(merge_group) > 1 else []
        }
        
        processed_names.add(seed_name)
    
    # Phase 2: if the category count still exceeds the target, try further strict merges.
    print(f"Phase 2: Current category count: {len(merged_categories)}, target: {target_count}")
    if len(merged_categories) > target_count:
        print("Continuing to merge with strict permission domain matching...")
        # Use the merged categories as the new candidate list.
        phase2_category_list = list(merged_categories.items())
        merged_categories = {}
        processed_names = set()
        
        # Only merge categories with highly consistent permission domains; do not force the target count.
        while len(processed_names) < len(phase2_category_list):
            seed_candidates = [(name, info) for name, info in phase2_category_list 
                              if name not in processed_names]
            if not seed_candidates:
                break
            
            seed_name, seed_info = max(seed_candidates, key=lambda x: x[1]['frequency'])
            
            merge_group = [seed_name]
            seed_definitions = [seed_info['category_definition']]
            total_count = seed_info['frequency']
            merged_from_list = seed_info.get('merged_from', [])
            
            # Try merging other categories with strict permission-domain matching.
            for other_name, other_info in phase2_category_list:
                if other_name in processed_names or other_name == seed_name:
                    continue
                
                # Strictly check whether categories can be merged.
                if can_merge_for_permission_analysis(
                    client, seed_name, seed_info['category_definition'],
                    other_name, other_info['category_definition'],
                    {}, {}  # Features are no longer needed; judge directly from definitions.
                ):
                    merge_group.append(other_name)
                    processed_names.add(other_name)
                    total_count += other_info['frequency']
                    seed_definitions.append(other_info['category_definition'])
                    merged_from_list.extend(other_info.get('merged_from', [other_name]))
            
            merged_name, merged_definition = generate_merged_category(
                client, merge_group, seed_definitions, seed_name, seed_info['category_definition']
            )
            
            merged_categories[merged_name] = {
                'category_name': merged_name,
                'category_definition': merged_definition,
                'frequency': total_count,
                'merged_from': merged_from_list if len(merged_from_list) > 0 else merge_group if len(merge_group) > 1 else []
            }
            
            processed_names.add(seed_name)
        
        # Handle remaining unmerged Phase 2 categories without forcing merges.
        remaining = [(name, info) for name, info in phase2_category_list if name not in processed_names]
        if remaining:
            print(f"Phase 2: Keeping {len(remaining)} categories separate (permission domains differ)")
            for remaining_name, remaining_info in remaining:
                merged_categories[remaining_name] = remaining_info
    else:
        # If the category count is already <= target after Phase 1, handle remaining unmerged categories.
        remaining = [(name, info) for name, info in category_list if name not in processed_names]
        if remaining:
            print(f"Phase 1: Attempting to merge {len(remaining)} remaining categories (strict matching only)...")
            # Sort existing categories by frequency and prefer merging into high-frequency categories.
            sorted_existing = sorted(
                merged_categories.items(),
                key=lambda x: x[1]['frequency'],
                reverse=True
            )
            
            for remaining_name, remaining_info in remaining:
                merged_into_existing = False
                remaining_def = remaining_info['definitions'][0] if remaining_info['definitions'] else ""
                
                # Try merging into existing categories with strict permission-domain matching.
                for existing_name, existing_info in sorted_existing:
                    if can_merge_for_permission_analysis(
                        client, existing_name, existing_info['category_definition'],
                        remaining_name, remaining_def,
                        {}, {}
                    ):
                        # Merge into an existing category.
                        print(f"  Merging '{remaining_name}' into '{existing_name}'")
                        
                        # Determine whether a new category name is needed.
                        should_generate, final_name, final_def = should_generate_new_category_name(
                            client, existing_name, existing_info['category_definition'],
                            remaining_name, remaining_def
                        )
                        
                        if should_generate and final_name and final_def:
                            # A new category name is needed; remove the old category and add the new one.
                            old_frequency = existing_info['frequency']
                            old_merged_from = existing_info.get('merged_from', [])
                            
                            # Remove the old category.
                            del merged_categories[existing_name]
                            
                            # Add the new category.
                            merged_categories[final_name] = {
                                'category_name': final_name,
                                'category_definition': final_def,
                                'frequency': old_frequency + remaining_info['count'],
                                'merged_from': old_merged_from + [remaining_name]
                            }
                            print(f"    Created new category '{final_name}' to better represent merged categories")
                        else:
                            # Use the existing category name or a more appropriate category name.
                            if final_name != existing_name:
                                # The category name needs to be updated using the incoming category name.
                                old_frequency = existing_info['frequency']
                                old_merged_from = existing_info.get('merged_from', [])
                                
                                # Remove the old category.
                                del merged_categories[existing_name]
                                
                                # Add the updated category.
                                merged_categories[final_name] = {
                                    'category_name': final_name,
                                    'category_definition': existing_info['category_definition'],
                                    'frequency': old_frequency + remaining_info['count'],
                                    'merged_from': old_merged_from + [remaining_name]
                                }
                            else:
                                # Use the existing category name and update it directly.
                                existing_info['frequency'] += remaining_info['count']
                                existing_info['merged_from'].extend([remaining_name])
                        
                        merged_into_existing = True
                        break
                
                # If it cannot be merged into an existing category, add it as a new category without limiting the count.
                if not merged_into_existing:
                    merged_categories[remaining_name] = {
                        'category_name': remaining_name,
                        'category_definition': remaining_def,
                        'frequency': remaining_info['count'],
                        'merged_from': []
                    }
                    print(f"  Adding '{remaining_name}' as new category (permission domain differs)")
            
            processed_names.update([name for name, _ in remaining])
    
    print(f"Merging completed: {len(category_freq)} categories -> {len(merged_categories)} categories")
    print(f"Note: Final count ({len(merged_categories)}) may differ from target ({target_count}) to maintain permission domain consistency")
    return merged_categories


def analyze_permission_features(client, category_name: str, category_definition: str) -> Dict[str, Any]:
    """
    Analyze permission features for a category.
    
    Returns:
        Dictionary containing permission features.
    """
    prompt = f"""Analyze the permission features of the following API category for permission analysis research.

Category name: {category_name}
Category definition: {category_definition}

Analyze and return the following permission features in JSON format:
{{
    "permission_type": "read/write/execute/mixed",  // Permission type: read, write, execute, or mixed.
    "resource_location": "local/remote/cloud/mixed",  // Resource location: local, remote, cloud, or mixed.
    "risk_level": "low/medium/high/critical",  // Security risk level.
    "auth_method": "api_key/oauth/token/credential/none/mixed",  // Authentication method.
    "sensitive_data": true/false,  // Whether sensitive data is involved.
    "privilege_scope": "Describe the permission scope"  // Permission-scope description.
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={
                'permission_type': 'mixed',
                'resource_location': 'mixed',
                'risk_level': 'medium',
                'auth_method': 'mixed',
                'sensitive_data': False,
                'privilege_scope': ''
            }
        )
        return result if result else {}
    except Exception as e:
        print(f"Error analyzing permission features: {e}")
        return {}


def find_most_similar_category(client, remaining_name: str, remaining_def: str, 
                                existing_categories: List[Tuple[str, Dict]]) -> Tuple[Optional[str], Optional[Dict], float]:
    """
    Find the existing category most similar to the remaining category.
    
    Args:
        client: OpenAI client.
        remaining_name: Remaining category name.
        remaining_def: Remaining category definition.
        existing_categories: Existing category list, where each item is a (name, info) tuple.
        
    Returns:
        (most similar category name, category info, similarity score), or (None, None, 0.0).
    """
    if not existing_categories:
        return None, None, 0.0
    
    # Build the list of existing categories for LLM evaluation.
    category_list_text = []
    for idx, (name, info) in enumerate(existing_categories, 1):
        category_list_text.append(f"{idx}. {name}: {info['category_definition']}")
    
    prompt = f"""Given an API category that needs to be merged, find the most similar category from the existing category list below.

Category to merge:
Name: {remaining_name}
Definition: {remaining_def}

Existing category list:
{chr(10).join(category_list_text)}

Evaluate the similarity between each existing category and the category to merge by considering:
1. Permission-type similarity (read/write/execute)
2. Resource-location similarity (local/remote/cloud)
3. Security risk-level similarity
4. Authentication-method similarity
5. Functional-domain similarity

Return the most similar category index (1-{len(existing_categories)}) and a similarity score (0.0-1.0).

Return JSON in this format:
{{
    "best_match_index": 1,  // Index of the most similar category, starting from 1.
    "similarity_score": 0.85,  // Similarity score from 0.0 to 1.0.
    "reason": "Explain the merge rationale"
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={'best_match_index': 1, 'similarity_score': 0.5, 'reason': ''}
        )
        
        if result:
            best_idx = result.get('best_match_index', 1)
            similarity_score = result.get('similarity_score', 0.5)
            reason = result.get('reason', '')
            
            # Ensure the index is within the valid range.
            if 1 <= best_idx <= len(existing_categories):
                best_name, best_info = existing_categories[best_idx - 1]
                print(f"    Best match: '{best_name}' (similarity: {similarity_score:.2f}, reason: {reason})")
                return best_name, best_info, similarity_score
    except Exception as e:
        print(f"Error finding most similar category: {e}")
    
    # If an error occurs, return the first category as the default.
    if existing_categories:
        return existing_categories[0][0], existing_categories[0][1], 0.5
    
    return None, None, 0.0


def merge_single_category_with_existing(client, new_category: Dict, existing_categories: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Merge a single new category into the existing categories.
    
    Args:
        client: OpenAI client.
        new_category: New category dictionary containing category_name and category_definition.
        existing_categories: Existing category dictionary keyed by category name.
        
    Returns:
        Updated category dictionary.
    """
    new_name = new_category.get('category_name', '').strip()
    new_def = new_category.get('category_definition', '').strip()
    
    if not new_name:
        return existing_categories
    
    # If the new category name already exists, increment its frequency directly.
    if new_name in existing_categories:
        existing_categories[new_name]['frequency'] += 1
        return existing_categories
    
    # Find the most similar existing category.
    existing_category_list = [(name, info) for name, info in existing_categories.items()]
    best_match_name, best_match_info, similarity_score = find_most_similar_category(
        client, new_name, new_def, existing_category_list
    )
    
    if best_match_name:
        # Merge into the most similar category.
        existing_categories[best_match_name]['frequency'] += 1
        
        # Update the merged_from list.
        if 'merged_from' not in existing_categories[best_match_name]:
            existing_categories[best_match_name]['merged_from'] = []
        if new_name not in existing_categories[best_match_name]['merged_from']:
            existing_categories[best_match_name]['merged_from'].append(new_name)
    
    return existing_categories


def load_existing_categories(json_path: str) -> Dict[str, Dict]:
    """
    Load the existing 10 categories from a JSON file, using the merged_categories field.
    
    Args:
        json_path: JSON file path.
        
    Returns:
        Category dictionary keyed by category name, with category info as values.
    """
    print(f"Loading existing categories from: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Read the final merged categories from the merged_categories field.
    merged_categories = data.get('merged_categories', {})
    
    # Validate the category count.
    expected_count = data.get('total_categories_after_semantic_merge', 10)
    actual_count = len(merged_categories)
    
    if actual_count != expected_count:
        print(f"Warning: Expected {expected_count} categories, but found {actual_count}")
    
    # Convert to the standard format and ensure frequency and merged_from fields exist.
    result = {}
    for name, info in merged_categories.items():
        result[name] = {
            'category_name': name,
            'category_definition': info.get('category_definition', ''),
            'frequency': info.get('frequency', 0),
            'merged_from': info.get('merged_from', [])
        }
    
    print(f"Loaded {len(result)} existing categories from merged_categories:")
    for i, name in enumerate(result.keys(), 1):
        print(f"  {i}. {name}")
    
    return result


def can_merge_for_permission_analysis(client, name1: str, def1: str, name2: str, def2: str,
                                      features1: Dict, features2: Dict) -> bool:
    """
    Determine whether two categories can be merged for permission analysis.
    
    Merge conditions; all must be satisfied:
    1. Similar permission type, such as both read, both write, or both execute.
    2. Similar resource location, such as both local, both remote, or both cloud.
    3. Similar security risk level.
    4. Similar authentication method.
    5. **Permission-domain consistency** (core requirement): resource type, service type, and permission scope must be highly similar.
    """
    # First check permission-feature similarity.
    if features1 and features2:
        # Permission type match.
        perm1 = features1.get('permission_type', 'mixed')
        perm2 = features2.get('permission_type', 'mixed')
        if perm1 != 'mixed' and perm2 != 'mixed' and perm1 != perm2:
            return False
        
        # Resource location match.
        loc1 = features1.get('resource_location', 'mixed')
        loc2 = features2.get('resource_location', 'mixed')
        if loc1 != 'mixed' and loc2 != 'mixed' and loc1 != loc2:
            return False
        
        # Similar risk levels; adjacent levels may be merged.
        risk_levels = ['low', 'medium', 'high', 'critical']
        risk1 = features1.get('risk_level', 'medium')
        risk2 = features2.get('risk_level', 'medium')
        idx1 = risk_levels.index(risk1) if risk1 in risk_levels else 1
        idx2 = risk_levels.index(risk2) if risk2 in risk_levels else 1
        if abs(idx1 - idx2) > 1:  # Only adjacent risk levels may be merged.
            return False
    
    # Use the LLM for strict semantic judgment.
    prompt = f"""Determine whether the following two API categories can be merged for permission analysis. **The merge conditions are strict, and all must be satisfied to allow merging**.

**Strict merge conditions**:
1. **Permission domains must be highly consistent**:
   - The accessed resource types must be the same, such as databases, social media, or cloud infrastructure.
   - The service types must be the same, such as database systems, messaging platforms, or collaboration tools.
   - The permission scopes must be similar, such as read operations, write operations, or execute operations.

2. **Permission types must be similar** (read/write/execute)

3. **Resource locations must be similar** (local/remote/cloud)

4. **Security risk levels must be close**

5. **Authentication methods must be similar**

**Allowed merge cases** (highly consistent permission domains):
- Different database systems (MongoDB + PostgreSQL)
- Different social media platforms (Twitter + Facebook)
- Different messaging platforms (Telegram + WhatsApp)
- Different cloud infrastructure services (AWS + Azure, if both are infrastructure management)

Category 1:
Name: {name1}
Definition: {def1}

Category 2:
Name: {name2}
Definition: {def2}

**Analyze carefully**:
1. Do these two categories access the same resource type?
2. Do these two categories have the same service type?
3. Are their permission scopes similar?
4. Would merging them blur the permission boundary?

**If the permission domains are inconsistent, return false even if other conditions are similar**.

Return JSON in this format:
{{
    "can_merge": true/false,
    "reason": "Merge or rejection reason; explain in detail whether the permission domains match.",
    "permission_domain_match": true/false,  // Whether permission domains match.
    "resource_type_match": true/false,  // Whether resource types match.
    "service_type_match": true/false  // Whether service types match.
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={
                'can_merge': False, 
                'reason': '',
                'permission_domain_match': False,
                'resource_type_match': False,
                'service_type_match': False
            }
        )
        
        if result:
            can_merge = result.get('can_merge', False)
            reason = result.get('reason', '')
            permission_domain_match = result.get('permission_domain_match', False)
            resource_type_match = result.get('resource_type_match', False)
            service_type_match = result.get('service_type_match', False)
            
            # If the permission domain does not match, force False.
            if not permission_domain_match or not resource_type_match or not service_type_match:
                if can_merge:
                    print(f"  Rejecting merge '{name1}' and '{name2}': Permission domain mismatch (domain_match={permission_domain_match}, resource_match={resource_type_match}, service_match={service_type_match})")
                return False
            
            if can_merge:
                print(f"  Merging '{name1}' and '{name2}': {reason}")
            else:
                print(f"  Rejecting merge '{name1}' and '{name2}': {reason}")
            return can_merge
    except Exception as e:
        print(f"Error judging merge possibility: {e}")
    
    return False


def should_generate_new_category_name(client, existing_name: str, existing_def: str,
                                      new_category_name: str, new_category_def: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Determine whether a new category name is needed to better summarize the merged category.
    
    Args:
        client: OpenAI client.
        existing_name: Existing category name.
        existing_def: Existing category definition.
        new_category_name: Incoming category name to merge.
        new_category_def: Incoming category definition to merge.
        
    Returns:
        (whether a new name is needed, new category name, new category definition).
    """
    prompt = f"""After merging the following two API categories, determine whether the existing category name can accurately summarize the merged category.

Existing category:
Name: {existing_name}
Definition: {existing_def}

Incoming category to merge:
Name: {new_category_name}
Definition: {new_category_def}

**Category naming constraints**:
1. Category names must be concise: no more than 5-6 words, such as "Database Management" or "Cloud Infrastructure Management".
2. Avoid overly specific descriptive terms:
   - Avoid modifiers such as "AI-Driven", "Schema-Driven", and "Data-Driven".
   - Avoid overly specific business terms such as "Governance" and "Orchestration".
   - Prefer standardized short names, such as "AI and Machine Learning Services" instead of "AI-Driven Data and Schema Governance Services".
3. Prefer industry-standard terminology and keep names concise and professional.

Please determine:
1. Can the existing category name "{existing_name}" accurately summarize both merged categories, and does it satisfy the naming constraints?
2. Can the incoming category name "{new_category_name}" accurately summarize both merged categories, and does it satisfy the naming constraints?

If neither category name accurately summarizes the merged category, or if the names violate the constraints by being too long or too specific, generate a new concise and professional category name and definition.

Return JSON in this format:
{{
    "existing_name_adequate": true/false,  // Whether the existing category name is adequate and satisfies the constraints.
    "new_name_adequate": true/false,  // Whether the incoming category name is adequate and satisfies the constraints.
    "should_generate_new": true/false,  // Whether a new name should be generated.
    "new_category_name": "New category name, if needed; must be concise, no more than 4-5 words, and avoid overly specific descriptions.",  // Provide a new name if should_generate_new is true.
    "new_category_definition": "New category definition, if needed.",  // Provide a new definition if should_generate_new is true.
    "reason": "Judgment rationale, including whether the naming constraints are satisfied."
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={
                'existing_name_adequate': True,
                'new_name_adequate': False,
                'should_generate_new': False,
                'new_category_name': existing_name,
                'new_category_definition': existing_def,
                'reason': ''
            }
        )
        
        if result:
            should_generate = result.get('should_generate_new', False)
            if should_generate:
                new_name = result.get('new_category_name', existing_name)
                new_def = result.get('new_category_definition', existing_def)
                reason = result.get('reason', '')
                
                # Validate whether the generated category name satisfies the constraints.
                word_count = len(new_name.split())
                if word_count > 5:
                    print(f"    Warning: Generated name '{new_name}' has {word_count} words, may be too long")
                
                # Check whether it contains overly specific descriptive terms.
                overly_specific_patterns = ['Driven', 'Governance', 'Orchestration', 'Schema-Driven', 'AI-Driven', 'Data-Driven']
                if any(pattern in new_name for pattern in overly_specific_patterns):
                    print(f"    Warning: Generated name '{new_name}' may be too specific")
                
                print(f"    Generating new category name: '{new_name}' (reason: {reason})")
                return True, new_name, new_def
            else:
                # Decide which existing name to use.
                existing_adequate = result.get('existing_name_adequate', True)
                new_adequate = result.get('new_name_adequate', False)
                if existing_adequate:
                    return False, existing_name, None
                elif new_adequate:
                    return False, new_category_name, None
                else:
                    # If neither is adequate but no new name is required, use the existing name.
                    return False, existing_name, None
    except Exception as e:
        print(f"Error judging category name adequacy: {e}")
    
    # Use the existing name by default.
    return False, existing_name, None


def generate_merged_category(client, merge_group: List[str], definitions: List[str], 
                            seed_name: str, seed_definition: str) -> Tuple[str, str]:
    """
    Generate the merged category name and definition.
    Use an existing category name if it accurately summarizes the merged category; otherwise generate a new name.
    Optimization: ensure generated category names are professional and precise, avoiding vague, overly long, or overly specific wording.
    """
    if len(merge_group) == 1:
        return seed_name, seed_definition
    
    # If multiple categories will be merged, first judge whether the existing name is adequate.
    if len(merge_group) == 2:
        # For two categories, judge whether the existing name is adequate.
        other_name = merge_group[1] if merge_group[0] == seed_name else merge_group[0]
        other_def = definitions[1] if definitions[0] == seed_definition else definitions[0]
        
        should_generate, final_name, final_def = should_generate_new_category_name(
            client, seed_name, seed_definition, other_name, other_def
        )
        
        if should_generate and final_name and final_def:
            return final_name, final_def
        elif final_name and final_name != seed_name:
            # Use the other category name.
            return final_name, seed_definition
    
    # For multiple categories or when a new name is needed, use the LLM to generate it.
    prompt = f"""Based on the following category list, generate a merged API category name and definition for permission analysis research.

Categories to merge:
{chr(10).join([f"- {name}" for name in merge_group])}

Definitions of all categories:
{chr(10).join([f"{i+1}. {name}: {defn}" for i, (name, defn) in enumerate(zip(merge_group, definitions))])}

**Strict naming requirements**:
1. **Category names must be concise**:
   - No more than 4-5 words, such as "Database Management" or "Cloud Infrastructure Management".
   - Avoid overly long descriptive names. For example, "AI-Driven Data and Schema Governance Services" is too long and should be simplified to "AI and Machine Learning Services" or "Data Governance Services".

2. **Avoid overly specific descriptive terms**:
   - Avoid modifiers such as "AI-Driven", "Schema-Driven", and "Data-Driven".
   - Avoid overly specific business terms such as "Governance" and "Orchestration" unless they are core functionality.
   - Prefer standardized short names.

3. **Use industry-standard terminology**:
   - If database systems are involved, such as MongoDB, PostgreSQL, or Redis, use "Database Management".
   - If HTTP clients and web data retrieval are involved, such as axios, requests, or web scraping, use "Web Data Retrieval" or "HTTP Client Services".
   - If file system operations are involved, use "File System Operations".
   - If AI/ML services are involved, use "AI and Machine Learning Services" instead of "AI-Driven Data and Schema Governance Services".
   - If data governance and metadata are involved, use "Data Governance Services" or "Metadata Management Services" instead of "AI-Driven Data and Schema Governance Services".
   
4. **Naming examples**:
   - Good names: "Database Management", "AI and Machine Learning Services", "Data Governance Services", "Cloud Infrastructure Management"
   - Bad names: "AI-Driven Data and Schema Governance Services" (too long and too specific), "External Service Interaction APIs" (uses "External")

5. If an existing category name, such as "{seed_name}", accurately summarizes all categories and satisfies the naming requirements, prefer the existing name.

6. If the existing category name does not summarize the categories well or violates the naming constraints, generate a new concise and professional category name.

7. The category definition must clearly state:
   - Specific service providers or API types included, such as "MongoDB, PostgreSQL" rather than "database systems".
   - Permission scope (read/write/execute).
   - Resource location (local/remote/cloud).
   - Security risks and sensitive resources.
   - Authentication method.
   - Clear distinctions from other categories.

8. Ensure the merged category is suitable for permission analysis and has clear permission boundaries.

Return JSON in this format:
{{
    "category_name": "Merged category name; must be concise, no more than 4-5 words, avoid overly specific descriptions, and prefer standard terms.",
    "category_definition": "Detailed category definition; must specify service providers and API types.",
    "use_existing_name": true/false,  // Whether an existing name was used.
    "reason": "Reason for selecting or generating the category name, including naming basis and constraint compliance."
}}
"""
    
    try:
        result = generate_content_openai(
            client=client,
            prompt=prompt,
            model='qwen3-max-preview',
            repeat=3,
            output_check={
                'category_name': seed_name,
                'category_definition': seed_definition,
                'use_existing_name': True,
                'reason': ''
            }
        )
        
        if result:
            new_name = result.get('category_name', seed_name)
            new_def = result.get('category_definition', seed_definition)
            use_existing = result.get('use_existing_name', True)
            reason = result.get('reason', '')
            
            # Validate whether the generated category name satisfies the constraints.
            word_count = len(new_name.split())
            if word_count > 5:
                print(f"    Warning: Generated name '{new_name}' has {word_count} words, may be too long")
            
            # Check whether it contains overly specific descriptive terms.
            overly_specific_patterns = ['Driven', 'Governance', 'Orchestration', 'Schema-Driven', 'AI-Driven', 'Data-Driven']
            if any(pattern in new_name for pattern in overly_specific_patterns):
                print(f"    Warning: Generated name '{new_name}' may be too specific, consider simplifying")
            
            if use_existing and new_name == seed_name:
                print(f"    Using existing category name '{seed_name}' (reason: {reason})")
            else:
                print(f"    Generated new category name '{new_name}' (reason: {reason})")
            
            return new_name, new_def
    except Exception as e:
        print(f"Error generating merged category: {e}")
    
    return seed_name, seed_definition


def main():
    """Main function."""
    # Configuration file path.
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'tool_analyzer',
        'api_cache_external.json'
    )
    
    if not os.path.exists(json_path):
        print(f"Error: File not found {json_path}")
        return
    
    # Load API data.
    api_list = load_api_data(json_path)
    
    if len(api_list) < 50:
        print(f"Error: Insufficient API count (need at least 50, currently {len(api_list)})")
        return
    
    # Initialize client.
    print("Initializing LLM client...")
    client = get_openai_client()
    
    # Steps 1 and 2: repeatedly sample and classify.
    all_categories = []
    num_rounds = 20
    
    print(f"\nStarting {num_rounds} rounds of sampling and classification...")
    for round_num in range(1, num_rounds + 1):
        print(f"\n{'='*60}")
        print(f"Round {round_num}/{num_rounds}")
        print(f"{'='*60}")
        
        # Random sample with a fixed size of 50.
        sampled_apis = sample_apis(api_list, min_count=50, max_count=50)
        print(f"Sampled {len(sampled_apis)} APIs")
        
        # Classify.
        categories = classify_apis_with_llm(client, sampled_apis)
        
        if categories:
            all_categories.append(categories)
            print(f"This round got {len(categories)} categories")
            # Print category names from this round.
            print("Category names in this round:")
            for i, cat in enumerate(categories, 1):
                category_name = cat.get('category_name', 'Unknown')
                print(f"  {i}. {category_name}")
        else:
            print("This round classification failed, skipping")
        
        # Add delay to avoid overly frequent API calls.
        if round_num < num_rounds:
            time.sleep(2)
    
    if not all_categories:
        print("Error: All rounds of classification failed")
        return
    
    print(f"\nAll rounds completed, got {len(all_categories)} rounds of valid classification results")
    
    # Step 3: merge categories for permission analysis.
    print("\n" + "="*60)
    print("Merging categories for permission analysis...")
    print("="*60)
    merged_categories = merge_categories_for_permission_analysis(client, all_categories, target_count=10)
    
    # Step 4: sort by frequency.
    sorted_categories = sorted(
        merged_categories.items(),
        key=lambda x: x[1]['frequency'],
        reverse=True
    )
    
    # Step 5: limit to 10 categories by merging extra categories into the top 10.
    target_count = 10
    if len(sorted_categories) > target_count:
        print(f"\nLimiting categories from {len(sorted_categories)} to {target_count}")
        print(f"Merging {len(sorted_categories) - target_count} categories into top {target_count} categories...")
        
        # Keep the top 10 categories.
        top_categories = dict(sorted_categories[:target_count])
        remaining_categories = sorted_categories[target_count:]
        
        # Merge remaining categories into the most similar top-10 category.
        for remaining_name, remaining_info in remaining_categories:
            remaining_def = remaining_info['category_definition']
            
            # Find the most similar category.
            top_category_list = [(name, info) for name, info in top_categories.items()]
            best_match_name, best_match_info, similarity_score = find_most_similar_category(
                client, remaining_name, remaining_def, top_category_list
            )
            
            if best_match_name:
                print(f"  Merging '{remaining_name}' (freq: {remaining_info['frequency']}) into '{best_match_name}' (similarity: {similarity_score:.2f})")
                
                # Update frequency.
                top_categories[best_match_name]['frequency'] += remaining_info['frequency']
                
                # Update the merged_from list.
                if 'merged_from' not in top_categories[best_match_name]:
                    top_categories[best_match_name]['merged_from'] = []
                if remaining_name not in top_categories[best_match_name]['merged_from']:
                    top_categories[best_match_name]['merged_from'].append(remaining_name)
                # Also add the merged_from entries from the merged category itself.
                if remaining_info.get('merged_from'):
                    for merged_name in remaining_info['merged_from']:
                        if merged_name not in top_categories[best_match_name]['merged_from']:
                            top_categories[best_match_name]['merged_from'].append(merged_name)
        
        # Update sorted_categories with the merged result.
        sorted_categories = sorted(
            top_categories.items(),
            key=lambda x: x[1]['frequency'],
            reverse=True
        )
        print(f"Merge completed. Final category count: {len(sorted_categories)}")
    
    # Build the final result.
    final_result = {
        'total_rounds': num_rounds,
        'total_categories_before_merge': sum(len(cats) for cats in all_categories),
        'total_categories_after_semantic_merge': len(sorted_categories),
        'merged_categories': {}
    }
    
    # Save merged categories.
    for category_name, category_info in sorted_categories:
        final_result['merged_categories'][category_name] = category_info
    
    # Also save original classification results for reference.
    final_result['rounds'] = []
    for round_idx, round_categories in enumerate(all_categories, 1):
        round_result = {
            'round': round_idx,
            'categories': round_categories
        }
        final_result['rounds'].append(round_result)
    
    # Output results.
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'api_classification_result.json'
    )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, indent=4, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("Classification results saved to:", output_path)
    print(f"{'='*60}")
    print(f"\nTotal categories before merge: {final_result['total_categories_before_merge']}")
    print(f"Total categories after merge: {final_result['total_categories_after_semantic_merge']}")
    print(f"Total rounds: {len(all_categories)}")
    
    # Print the merged category list.
    print(f"\n{'='*60}")
    print("Final merged categories (sorted by frequency):")
    print(f"{'='*60}")
    for i, (name, info) in enumerate(sorted_categories, 1):
        print(f"{i}. {name} (frequency: {info['frequency']})")
        if info.get('merged_from'):
            print(f"   Merged from: {', '.join(info['merged_from'])}")
    
    # Print a per-round summary of classification results.
    print(f"\n{'='*60}")
    print("Summary of original classification results by round:")
    print(f"{'='*60}")
    for round_idx, round_categories in enumerate(all_categories, 1):
        print(f"\nRound {round_idx}: {len(round_categories)} categories")
        for i, cat in enumerate(round_categories, 1):
            print(f"  {i}. {cat.get('category_name', 'Unknown')}")


def main_merge_with_existing():
    """Main function: sample 80 rounds, generate 10 categories per round, and merge them one by one into the existing 10 categories."""
    # Configuration file path.
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'tool_analyzer',
        'api_cache_external.json'
    )
    
    if not os.path.exists(json_path):
        print(f"Error: File not found {json_path}")
        return
    
    # Load existing categories.
    existing_result_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'api_classification_result.json'
    )
    
    if not os.path.exists(existing_result_path):
        print(f"Error: Existing classification result not found: {existing_result_path}")
        return
    
    existing_categories = load_existing_categories(existing_result_path)
    
    # Load API data.
    api_list = load_api_data(json_path)
    
    if len(api_list) < 50:
        print(f"Error: Insufficient API count (need at least 50, currently {len(api_list)})")
        return
    
    # Initialize client.
    print("Initializing LLM client...")
    client = get_openai_client()
    
    # Sample 80 rounds and generate 10 categories per round.
    num_rounds = 80
    total_categories_processed = 0
    
    print(f"\nStarting {num_rounds} rounds of sampling and classification...")
    print(f"Each round will generate 10 categories, total {num_rounds * 10} categories to merge")
    print(f"Existing categories: {list(existing_categories.keys())}")
    
    all_new_categories = []
    
    for round_num in range(1, num_rounds + 1):
        print(f"\n{'='*60}")
        print(f"Round {round_num}/{num_rounds}")
        print(f"{'='*60}")
        
        # Random sample with a fixed size of 50.
        sampled_apis = sample_apis(api_list, min_count=50, max_count=50)
        print(f"Sampled {len(sampled_apis)} APIs")
        
        # Classify, generating 10 categories per round.
        categories = classify_apis_with_llm(client, sampled_apis)
        
        if categories:
            all_new_categories.append(categories)
            print(f"This round got {len(categories)} categories")
            
            # Merge categories into the existing categories one by one.
            for idx, category in enumerate(categories, 1):
                existing_categories = merge_single_category_with_existing(
                    client, category, existing_categories
                )
                total_categories_processed += 1
                
                # Print progress every 100 processed categories.
                if total_categories_processed % 100 == 0:
                    print(f"  Processed {total_categories_processed} categories so far...")
        else:
            print("This round classification failed, skipping")
        
        # Add delay to avoid overly frequent API calls.
        if round_num < num_rounds:
            time.sleep(2)
    
    if not all_new_categories:
        print("Error: All rounds of classification failed")
        return
    
    print(f"\nAll rounds completed, processed {total_categories_processed} categories")
    
    # Sort by frequency.
    sorted_categories = sorted(
        existing_categories.items(),
        key=lambda x: x[1]['frequency'],
        reverse=True
    )
    
    # Build the final result.
    final_result = {
        'total_rounds': num_rounds,
        'total_categories_processed': total_categories_processed,
        'total_categories_after_merge': len(sorted_categories),
        'merged_categories': {}
    }
    
    # Save merged categories.
    for category_name, category_info in sorted_categories:
        final_result['merged_categories'][category_name] = category_info
    
    # Save original classification results for reference, keeping only the first few rounds as examples.
    final_result['rounds'] = []
    # Keep only the first 5 rounds as examples to avoid large files.
    for round_idx, round_categories in enumerate(all_new_categories[:5], 1):
        round_result = {
            'round': round_idx,
            'categories': round_categories
        }
        final_result['rounds'].append(round_result)
    
    # Output results to a new file.
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'api_classification_result_merged.json'
    )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, indent=4, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("Classification results saved to:", output_path)
    print(f"{'='*60}")
    print(f"\nTotal rounds: {num_rounds}")
    print(f"Total categories processed: {total_categories_processed}")
    print(f"Final category count: {len(sorted_categories)}")
    
    # Print the merged category list.
    print(f"\n{'='*60}")
    print("Final merged categories (sorted by frequency):")
    print(f"{'='*60}")
    for i, (name, info) in enumerate(sorted_categories, 1):
        print(f"{i}. {name} (frequency: {info['frequency']})")
        merged_from = info.get('merged_from', [])
        if merged_from:
            # Show only the first 5 merge sources.
            display_list = merged_from[:5]
            print(f"   Merged from: {', '.join(display_list)}")
            if len(merged_from) > 5:
                print(f"   ... and {len(merged_from) - 5} more")


if __name__ == "__main__":
    # Choose either the original main() or the new main_merge_with_existing().
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--merge':
        main_merge_with_existing()
    else:
        main()
