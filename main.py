#!/usr/bin/env python3
"""
订阅源合并与更新脚本
用于合并多个订阅源，进行去重和自定义处理，并最终生成一个 BASE58 编码的合并后配置
修改版：确保至少保留一个豆瓣资源
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


def test_site_latency(api_url: str) -> Optional[float]:
    """测试单个站点的延迟，返回延迟时间或None"""
    try:
        start_time = time.time()
        requests.head(api_url, timeout=5.0)
        end_time = time.time()
        return (end_time - start_time) * 1000
    except Exception:
        return None


def is_douban_resource(site: Dict[Any, Any]) -> bool:
    """判断是否为豆瓣资源"""
    # 检查name字段是否包含"豆瓣"
    if 'name' in site:
        name = site['name'].lower()
        if '豆瓣' in name or 'douban' in name:
            return True
    
    # 检查api字段URL是否包含douban
    if 'api' in site:
        api_url = site['api'].lower()
        if 'douban' in api_url:
            return True
    
    return False


def remove_prefixes_and_filter_sites(json_data: Dict[Any, Any], ttl_ms: Optional[int] = None, max_test: Optional[int] = None) -> Dict[Any, Any]:
    """去除前缀、去重、测试延迟并按ttl排序，同时确保保留豆瓣资源"""
    if 'api_site' not in json_data:
        return json_data
    
    print("开始去前缀、去重和延迟测试...")
    
    # 统一转换为字典格式
    if isinstance(json_data['api_site'], list):
        sites_dict = {}
        for i, site in enumerate(json_data['api_site']):
            sites_dict[f"api_{i+1}"] = site
        json_data['api_site'] = sites_dict
    
    # 第一步：收集所有站点并去前缀，同时标记豆瓣资源
    sites_info = []
    douban_sites = []  # 单独收集豆瓣资源
    
    for key, site in json_data['api_site'].items():
        if 'name' in site:
            name = site['name']
            # 去前缀：找到第一个'-'，去掉前面的部分
            if '-' in name:
                clean_name = name.split('-', 1)[1]  # 只分割第一个'-'
            else:
                clean_name = name
            
            site_info = {
                'key': key,
                'original_name': name,
                'clean_name': clean_name,
                'site': site.copy(),
                'is_douban': is_douban_resource(site)
            }
            
            sites_info.append(site_info)
            
            # 如果是豆瓣资源，也加入特殊列表
            if site_info['is_douban']:
                douban_sites.append(site_info)
        else:
            # 没有name字段的站点直接保留
            site_info = {
                'key': key,
                'original_name': 'Unknown',
                'clean_name': 'Unknown', 
                'site': site.copy(),
                'is_douban': is_douban_resource(site)
            }
            sites_info.append(site_info)
            
            if site_info['is_douban']:
                douban_sites.append(site_info)
    
    print(f"原始站点数: {len(sites_info)} 个")
    print(f"豆瓣资源数: {len(douban_sites)} 个")
    
    # 第二步：按清洁名称分组
    from collections import defaultdict
    name_groups = defaultdict(list)
    for site_info in sites_info:
        name_groups[site_info['clean_name']].append(site_info)
    
    duplicates = sum(1 for sites in name_groups.values() if len(sites) > 1)
    if duplicates > 0:
        print(f"发现 {duplicates} 组重复名称")
    
    # 第三步：对每组进行处理
    final_sites_with_ttl = []
    total_removed = 0
    tested_count = 0
    douban_preserved = None  # 记录保留的豆瓣资源
    
    for clean_name, sites in name_groups.items():
        if max_test and tested_count >= max_test:
            # 达到测试上限，但要特殊处理豆瓣资源
            for site_info in sites:
                site_info['site']['name'] = clean_name
                if site_info['is_douban'] and douban_preserved is None:
                    # 如果是豆瓣资源且还没有保留任何豆瓣资源，则保留
                    final_sites_with_ttl.append({
                        'key': site_info['key'],
                        'site': site_info['site'],
                        'ttl': 0  # 豆瓣资源设置较高优先级
                    })
                    douban_preserved = site_info
                    print(f"✓ 保留豆瓣资源: {clean_name} (未测试)")
                elif not site_info['is_douban']:
                    # 非豆瓣资源直接保留（无TTL字段）
                    final_sites_with_ttl.append({
                        'key': site_info['key'],
                        'site': site_info['site'],
                        'ttl': float('inf')  # 未测试的站点排在最后
                    })
            continue
            
        if len(sites) == 1:
            # 只有一个站点
            site_info = sites[0]
            site_info['site']['name'] = clean_name  # 更新名称去掉前缀
            
            # 测试延迟（无论是否有TTL限制）
            if 'api' in site_info['site']:
                tested_count += 1
                print(f"测试: {clean_name}")
                latency = test_site_latency(site_info['site']['api'])
                
                if latency is not None:
                    # 添加TTL字段
                    site_info['site']['ttl'] = int(latency)
                    print(f"  延迟: {latency:.0f}ms")
                    
                    # 如果是豆瓣资源，优先保留
                    if site_info['is_douban']:
                        final_sites_with_ttl.append({
                            'key': site_info['key'],
                            'site': site_info['site'],
                            'ttl': latency
                        })
                        if douban_preserved is None or latency < douban_preserved.get('ttl', float('inf')):
                            douban_preserved = {**site_info, 'ttl': latency}
                        print(f"  ✓ 豆瓣资源保留: {clean_name}")
                    else:
                        # 非豆瓣资源按TTL限制处理
                        if ttl_ms and latency > ttl_ms:
                            print(f"  超过TTL限制({ttl_ms}ms)，过滤")
                            total_removed += 1
                            continue
                        
                        final_sites_with_ttl.append({
                            'key': site_info['key'],
                            'site': site_info['site'],
                            'ttl': latency
                        })
                else:
                    print(f"  测试失败")
                    if site_info['is_douban']:
                        # 豆瓣资源即使测试失败也保留
                        site_info['site']['ttl'] = 5000  # 设置一个中等的TTL值
                        final_sites_with_ttl.append({
                            'key': site_info['key'],
                            'site': site_info['site'],
                            'ttl': 5000
                        })
                        if douban_preserved is None:
                            douban_preserved = {**site_info, 'ttl': 5000}
                        print(f"  ✓ 豆瓣资源保留(测试失败): {clean_name}")
                    elif ttl_ms:  # 如果设置了TTL限制，测试失败则过滤
                        total_removed += 1
                        continue
                    else:  # 否则保留，但设置一个很高的TTL值
                        site_info['site']['ttl'] = 9999
                        final_sites_with_ttl.append({
                            'key': site_info['key'],
                            'site': site_info['site'],
                            'ttl': 9999
                        })
            else:
                # 没有API字段的站点
                if site_info['is_douban']:
                    # 豆瓣资源保留
                    site_info['site']['ttl'] = 0
                    final_sites_with_ttl.append({
                        'key': site_info['key'],
                        'site': site_info['site'],
                        'ttl': 0
                    })
                    if douban_preserved is None:
                        douban_preserved = {**site_info, 'ttl': 0}
                    print(f"  ✓ 豆瓣资源保留(无API): {clean_name}")
                else:
                    # 非豆瓣资源直接保留，TTL设为0
                    site_info['site']['ttl'] = 0
                    final_sites_with_ttl.append({
                        'key': site_info['key'],
                        'site': site_info['site'],
                        'ttl': 0
                    })
        else:
            # 多个重名站点，需要去重
            print(f"\n处理重复组: \"{clean_name}\" ({len(sites)} 个站点)")
            
            best_site = None
            best_latency = float('inf')
            best_douban_site = None
            best_douban_latency = float('inf')
            
            # 分别处理豆瓣和非豆瓣资源
            douban_sites_in_group = [s for s in sites if s['is_douban']]
            non_douban_sites_in_group = [s for s in sites if not s['is_douban']]
            
            # 测试豆瓣资源
            for site_info in douban_sites_in_group:
                if max_test and tested_count >= max_test:
                    break
                if 'api' in site_info['site']:
                    tested_count += 1
                    latency = test_site_latency(site_info['site']['api'])
                    
                    if latency is not None:
                        print(f"  {site_info['original_name']} (豆瓣): {latency:.0f}ms")
                        if latency < best_douban_latency:
                            best_douban_latency = latency
                            best_douban_site = site_info
                    else:
                        print(f"  {site_info['original_name']} (豆瓣): FAILED")
                        # 豆瓣资源即使失败也可能被保留
                        if best_douban_site is None:
                            best_douban_site = site_info
                            best_douban_latency = 5000
            
            # 测试非豆瓣资源
            for site_info in non_douban_sites_in_group:
                if max_test and tested_count >= max_test:
                    break
                if 'api' in site_info['site']:
                    tested_count += 1
                    latency = test_site_latency(site_info['site']['api'])
                    
                    if latency is not None:
                        print(f"  {site_info['original_name']}: {latency:.0f}ms")
                        
                        # 如果有TTL限制，只考虑符合条件的站点
                        if ttl_ms and latency > ttl_ms:
                            print(f"    超过TTL限制({ttl_ms}ms)")
                            continue
                            
                        if latency < best_latency:
                            best_latency = latency
                            best_site = site_info
                    else:
                        print(f"  {site_info['original_name']}: FAILED")
            
            # 优先保留豆瓣资源
            if best_douban_site:
                best_douban_site['site']['name'] = clean_name
                best_douban_site['site']['ttl'] = int(best_douban_latency)
                final_sites_with_ttl.append({
                    'key': best_douban_site['key'],
                    'site': best_douban_site['site'],
                    'ttl': best_douban_latency
                })
                if douban_preserved is None or best_douban_latency < douban_preserved.get('ttl', float('inf')):
                    douban_preserved = {**best_douban_site, 'ttl': best_douban_latency}
                print(f"  -> ✓ 保留豆瓣资源: {best_douban_site['original_name']} (延迟: {best_douban_latency:.0f}ms)")
                total_removed += len(sites) - 1
            elif best_site:
                best_site['site']['name'] = clean_name
                best_site['site']['ttl'] = int(best_latency)
                final_sites_with_ttl.append({
                    'key': best_site['key'],
                    'site': best_site['site'],
                    'ttl': best_latency
                })
                print(f"  -> 保留: {best_site['original_name']} (延迟: {best_latency:.0f}ms)")
                total_removed += len(sites) - 1
            else:
                print(f"  -> 所有站点都不符合要求，全部过滤")
                total_removed += len(sites)
    
    # 确保至少有一个豆瓣资源被保留
    if douban_preserved is None and douban_sites:
        print(f"\n⚠️  警告：没有豆瓣资源通过测试，强制保留TTL最小的豆瓣资源")
        # 找到延迟最小的豆瓣资源（即使超过TTL限制）
        best_douban = None
        best_douban_ttl = float('inf')
        
        for douban_site in douban_sites:
            if 'api' in douban_site['site']:
                latency = test_site_latency(douban_site['site']['api'])
                if latency is not None and latency < best_douban_ttl:
                    best_douban_ttl = latency
                    best_douban = douban_site
                elif latency is None and best_douban is None:
                    # 如果没有找到可测试的，至少保留一个
                    best_douban = douban_site
                    best_douban_ttl = 9999
            elif best_douban is None:
                # 没有API的豆瓣资源
                best_douban = douban_site
                best_douban_ttl = 0
        
        if best_douban:
            best_douban['site']['ttl'] = int(best_douban_ttl)
            final_sites_with_ttl.append({
                'key': best_douban['key'],
                'site': best_douban['site'],
                'ttl': best_douban_ttl
            })
            print(f"✓ 强制保留豆瓣资源: {best_douban['clean_name']} (TTL: {best_douban_ttl:.0f}ms)")
    
    # 第四步：按TTL排序
    print(f"\n按TTL排序...")
    final_sites_with_ttl.sort(key=lambda x: x['ttl'])
    
    # 重新生成键名并构建最终结果
    final_sites = {}
    for i, site_data in enumerate(final_sites_with_ttl, 1):
        new_key = f"api_{i}"
        final_sites[new_key] = site_data['site']
    
    json_data['api_site'] = final_sites
    
    print(f"\n处理完成:")
    print(f"- 原始站点: {len(sites_info)} 个")
    print(f"- 去重/过滤: {total_removed} 个") 
    print(f"- 最终保留: {len(final_sites)} 个站点")
    print(f"- 已按TTL从小到大排序")
    if douban_preserved or any('豆瓣' in site.get('name', '').lower() or 'douban' in site.get('name', '').lower() or 'douban' in site.get('api', '').lower() for site in final_sites.values()):
        print(f"✓ 已确保保留豆瓣资源")
    
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
    print("=== 订阅源合并工具 (豆瓣资源保护版) ===")
    
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
    
    # 4. 去前缀、去重并过滤高延迟站点（保护豆瓣资源）
    merged_json = remove_prefixes_and_filter_sites(merged_json, ttl, max_test_sites)
    
    # 5. 应用自定义设置
    merged_json = apply_custom_settings(merged_json, cache_time)
    
    # 6. 编码与输出
    encode_and_save(merged_json)
    
    print("=== 合并完成 ===")


if __name__ == '__main__':
    main()
