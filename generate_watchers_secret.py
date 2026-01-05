#!/usr/bin/env python3
"""
Helper script to generate WATCHERS_CONFIG value for GitHub Secrets
Reads config.json and outputs the watchers array as a JSON string
"""

import json
import sys
import os


def main():
    config_path = "config.json"
    
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found!")
        print("Please create config.json first.")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        watchers = config.get('watchers', [])
        
        if not watchers:
            print("Error: No watchers found in config.json")
            sys.exit(1)
        
        # Convert watchers array to compact JSON string
        watchers_json = json.dumps(watchers, ensure_ascii=False, separators=(',', ':'))
        
        print("=" * 60)
        print("WATCHERS_CONFIG value for GitHub Secrets:")
        print("=" * 60)
        print(watchers_json)
        print("=" * 60)
        print("\nCopy the above JSON string and use it as the value for")
        print("the WATCHERS_CONFIG secret in GitHub repository settings.")
        print("\nGitHub → Settings → Secrets and variables → Actions → New repository secret")
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

