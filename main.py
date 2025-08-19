#!/usr/bin/env python3
"""
订阅源合并与更新脚本
用于合并多个订阅源，进行去重和自定义处理，并最终生成一个 BASE58 编码的合并后配置
"""

import os
import sys
import json
import base64
import base58
import time
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv


def load_config() -> tuple:
    """加载配置信息"""
    load_dotenv()
    
    subscription_urls = os.getenv('SUBSCRIPTION_URLS', '')
    if not subscription_urls:
        print("Error: SUBSCRIPTION_URLS environment variable is required")
        sys.exit(1)
    
    urls = [url.strip() for url in subscription_urls.split(',') if url.strip()]
    cache_time = os.getenv('CACHE_TIME')
    ttl = os.getenv('TTL')
    
    print(f"Loaded {len(urls)} subscription URLs")
    if cache_time:
        print(f"Cache time: {cache_time}")
    if ttl:
        print(f"TTL filter: {ttl}ms")
    
    max_test_sites = os.getenv('MAX_TEST_SITES')
    
    return urls, cache_time, int(ttl) if ttl else None, int(max_test_sites) if max_test_sites else None


def fetch_and_decode_subscription(url: str) -> Optional[Dict[Any, Any]]:
    """获取并解码订阅源"""
    try:
        print(f"Fetching: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        content = response.text.strip()
        
        # 尝试 BASE58 解码
        try:
            decoded_content = base58.b58decode(content).decode('utf-8')
            print(f"Successfully decoded BASE58 content from {url}")
        except Exception:
            # 如果 BASE58 解码失败，尝试 BASE64
            try:
                decoded_content = base64.b64decode(content).decode('utf-8')
                print(f"Successfully decoded BASE64 content from {url}")
            except Exception:
                # 如果都失败，假设内容是明文 JSON
                decoded_content = content
                print(f"Using plain text content from {url}")
        
        # 解析 JSON
        json_data = json.loads(decoded_content)
        return json_data
        
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from {url}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error processing {url}: {e}")
        return None


def check_api_latency(api_url: str, timeout_ms: int) -> bool:
    """检查 API 延迟是否在可接受范围内"""
    try:
        start_time = time.time()
        # 使用更短的超时时间来避免长时间等待
        response = requests.head(api_url, timeout=min(5.0, timeout_ms/1000))
        end_time = time.time()
        
        latency_ms = (end_time - start_time) * 1000
        is_fast = latency_ms <= timeout_ms
        print(f"  {api_url[:50]}... - {latency_ms:.0f}ms {'✓' if is_fast else '✗'}")
        return is_fast
        
    except Exception as e:
        print(f"  {api_url[:50]}... - FAILED ({type(e).__name__}) ✗")
        # 如果请求失败，认为延迟过高
        return False


def filter_high_latency_sites(json_data: Dict[Any, Any], ttl_ms: int, max_test: Optional[int] = None) -> Dict[Any, Any]:
    """过滤高延迟站点"""
    if 'api_site' not in json_data:
        return json_data
    
    # 处理 api_site 为字典的情况
    if isinstance(json_data['api_site'], dict):
        original_count = len(json_data['api_site'])
        filtered_sites = {}
        
        test_count = min(original_count, max_test) if max_test else original_count
        print(f"Testing {test_count}/{original_count} sites with TTL limit {ttl_ms}ms...")
        
        current = 0
        tested = 0
        for key, site in json_data['api_site'].items():
            if max_test and tested >= max_test:
                # 保留剩余未测试的站点
                filtered_sites[key] = site
                continue
            current += 1
            print(f"[{current}/{original_count}] Testing {site.get('name', 'Unknown')}:")
            
            if 'api' in site:
                if check_api_latency(site['api'], ttl_ms):
                    filtered_sites[key] = site
                tested += 1
            else:
                # 保留没有 API 字段的站点
                filtered_sites[key] = site
                print(f"  No API field - keeping site")
        
        json_data['api_site'] = filtered_sites
        filtered_count = len(filtered_sites)
        print(f"Filtered {original_count - filtered_count} sites, {filtered_count} remaining")
    else:
        # 处理 api_site 为列表的情况
        original_count = len(json_data['api_site'])
        filtered_sites = []
        
        print(f"Filtering sites with TTL > {ttl_ms}ms...")
        
        for site in json_data['api_site']:
            if 'api' in site:
                if check_api_latency(site['api'], ttl_ms):
                    filtered_sites.append(site)
                else:
                    print(f"Filtered out high latency site: {site.get('name', site['api'])}")
            else:
                # 保留没有 API 字段的站点
                filtered_sites.append(site)
        
        json_data['api_site'] = filtered_sites
        filtered_count = len(filtered_sites)
        print(f"Filtered {original_count - filtered_count} sites, {filtered_count} remaining")
    
    return json_data


def merge_subscriptions(subscription_list: List[Dict[Any, Any]]) -> Dict[Any, Any]:
    """合并订阅源并去重"""
    if not subscription_list:
        return {}
    
    # 使用第一个订阅源作为基础
    base_json = subscription_list[0].copy()
    
    if 'api_site' not in base_json:
        base_json['api_site'] = {}
    
    # 统一转换为字典格式
    if isinstance(base_json['api_site'], list):
        # 如果是列表，转换为字典
        sites_dict = {}
        for i, site in enumerate(base_json['api_site']):
            sites_dict[f"api_{i+1}"] = site
        base_json['api_site'] = sites_dict
    
    # 创建 set 用于去重
    existing_apis = set()
    for site in base_json['api_site'].values():
        if 'api' in site:
            existing_apis.add(site['api'])
    
    print(f"Base subscription has {len(base_json['api_site'])} sites")
    
    # 合并其他订阅源
    for i, subscription in enumerate(subscription_list[1:], 1):
        if 'api_site' not in subscription:
            continue
            
        added_count = 0
        sites_to_merge = subscription['api_site']
        
        # 处理不同格式的 api_site
        if isinstance(sites_to_merge, dict):
            sites_iter = sites_to_merge.values()
        else:
            sites_iter = sites_to_merge
        
        for site in sites_iter:
            if 'api' in site and site['api'] not in existing_apis:
                # 生成新的键名
                new_key = f"api_{len(base_json['api_site']) + 1}"
                base_json['api_site'][new_key] = site
                existing_apis.add(site['api'])
                added_count += 1
        
        print(f"Added {added_count} unique sites from subscription {i}")
    
    print(f"Final merged subscription has {len(base_json['api_site'])} sites")
    return base_json


def apply_custom_settings(merged_json: Dict[Any, Any], cache_time: Optional[str]) -> Dict[Any, Any]:
    """应用自定义设置"""
    if cache_time:
        merged_json['cache_time'] = cache_time
        print(f"Set cache time to: {cache_time}")
    
    return merged_json


def encode_and_save(merged_json: Dict[Any, Any], output_file: str = 'merged_config.b58') -> None:
    """编码并保存最终配置"""
    # 转换为格式化的 JSON 字符串（美化格式）
    json_str = json.dumps(merged_json, ensure_ascii=False, indent=2, sort_keys=True)
    
    print(f"JSON size before encoding: {len(json_str)} characters")
    
    # BASE58 编码
    encoded_content = base58.b58encode(json_str.encode('utf-8')).decode('utf-8')
    
    # 保存到文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(encoded_content)
    
    print(f"Merged configuration saved to: {output_file}")
    print(f"Encoded size: {len(encoded_content)} characters")
    print(f"Expansion ratio: {len(encoded_content)/len(json_str):.2f}x")


def main():
    """主函数"""
    print("=== 订阅源合并工具 ===")
    
    # 1. 加载配置
    urls, cache_time, ttl, max_test_sites = load_config()
    
    # 2. 获取和解码所有订阅源
    subscriptions = []
    for url in urls:
        json_data = fetch_and_decode_subscription(url)
        if json_data:
            subscriptions.append(json_data)
    
    if not subscriptions:
        print("Error: No valid subscriptions found")
        sys.exit(1)
    
    print(f"Successfully loaded {len(subscriptions)} subscriptions")
    
    # 3. 合并与去重
    merged_json = merge_subscriptions(subscriptions)
    
    # 4. 过滤高延迟站点（如果设置了 TTL）
    if ttl:
        print("Filtering merged subscription for high latency sites...")
        merged_json = filter_high_latency_sites(merged_json, ttl, max_test_sites)
    
    # 5. 应用自定义设置
    merged_json = apply_custom_settings(merged_json, cache_time)
    
    # 6. 编码与输出
    encode_and_save(merged_json)
    
    print("=== 合并完成 ===")


if __name__ == '__main__':
    main()
