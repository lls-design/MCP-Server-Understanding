#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge API categories based on permission analysis requirements.
Merge categories from existing classification results to ensure the final set
contains only 10 categories and is suitable for permission analysis.
"""

import json
import os
import sys
from typing import List, Dict, Tuple, Any
import dotenv

# Add project root to path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables.
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from utils.llm_call import get_openai_client, generate_content_openai
from scripts.api_classification import merge_categories_for_permission_analysis


def load_existing_categories(json_path: str) -> List[List[Dict]]:
    """
    Load category data from an existing classification result file.
    
    Args:
        json_path: JSON file path.
        
    Returns:
        Classification result list for all rounds.
    """
    print(f"Loading existing categories from: {json_path}")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return []
    
    all_categories = []
    
    # Prefer the rounds field, which contains original classification results.
    if 'rounds' in data and data['rounds']:
        print("Found 'rounds' field, loading original classification results...")
        for round_data in data['rounds']:
            categories = round_data.get('categories', [])
            if categories:
                all_categories.append(categories)
        print(f"Loaded {len(all_categories)} rounds from 'rounds' field")
    
    # If there is no rounds field but merged_categories exists, use merged_categories.
    elif 'merged_categories' in data and data['merged_categories']:
        print("Found 'merged_categories' field (no 'rounds' field), using merged categories...")
        merged = data['merged_categories']
        # Convert merged_categories into a single-round result.
        categories = []
        for name, info in merged.items():
            if isinstance(info, dict):
                categories.append({
                    'category_name': info.get('category_name', name),
                    'category_definition': info.get('category_definition', '')
                })
            else:
                # If info is not a dictionary, use name directly.
                categories.append({
                    'category_name': name,
                    'category_definition': ''
                })
        if categories:
            all_categories.append(categories)
        print(f"Loaded {len(categories)} categories from 'merged_categories' field")
    else:
        print("Warning: No 'rounds' or 'merged_categories' field found in the file")
    
    print(f"Total loaded: {len(all_categories)} rounds, {sum(len(cats) for cats in all_categories)} categories")
    return all_categories


def main():
    """Main function."""
    # Input file path.
    input_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'api_classification_result.json'
    )
    
    if not os.path.exists(input_path):
        print(f"Error: File not found {input_path}")
        return
    
    # Load existing classification results.
    all_categories = load_existing_categories(input_path)
    
    if not all_categories:
        print("Error: No categories found in the input file")
        return
    
    # Initialize client.
    print("Initializing LLM client...")
    client = get_openai_client()
    
    # Merge categories.
    print("\n" + "="*60)
    print("Merging categories for permission analysis...")
    print("="*60)
    merged_categories = merge_categories_for_permission_analysis(client, all_categories, target_count=10)
    
    # Sort by frequency.
    sorted_categories = sorted(
        merged_categories.items(),
        key=lambda x: x[1]['frequency'],
        reverse=True
    )
    
    # Build final result.
    final_result = {
        'total_rounds': len(all_categories),
        'total_categories_before_merge': sum(len(cats) for cats in all_categories),
        'total_categories_after_semantic_merge': len(merged_categories),
        'merged_categories': {}
    }
    
    # Save merged categories.
    for category_name, category_info in sorted_categories:
        final_result['merged_categories'][category_name] = category_info
    
    # Output result.
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'api_classification_result_merged.json'
    )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, indent=4, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("Merged categories saved to:", output_path)
    print(f"{'='*60}")
    print(f"\nMerging summary:")
    print(f"  Before merge: {final_result['total_categories_before_merge']} categories")
    print(f"  After merge: {final_result['total_categories_after_semantic_merge']} categories")
    print(f"\nFinal categories (sorted by frequency):")
    print("-" * 60)
    for i, (name, info) in enumerate(sorted_categories, 1):
        print(f"{i}. {name} (frequency: {info['frequency']})")
        if info.get('merged_from'):
            print(f"   Merged from: {', '.join(info['merged_from'])}")


if __name__ == "__main__":
    main()
