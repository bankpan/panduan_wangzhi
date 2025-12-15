#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
研招网官网严格判断程序
功能：基于4个必要条件严格判断是否是院校的校级研招网官网

必要条件（全部满足才判定为"是"）：
1. 必须是校级研招网，不能是院级研招网
2. 必须是中文的研招网
3. 必须是目标院校的研招网
4. 必须是官网，不能是第三方的网站
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from typing import Dict, Tuple, List
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('checker.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StrictGraduateChecker:
    """严格的研招网检查器（必要条件法）- 使用Playwright绕过反爬"""

    def __init__(self):
        """初始化检查器"""

        # 院级特征（URL路径）
        self.college_path_patterns = [
            '/college/', '/school/', '/dept/', '/department/',
            '/xy/', '/yuanxi/', '/xueyuan/', '/yx/',
            '/colleges/', '/schools/', '/departments/',
            '/yjsy/college/', '/graduate/school/',
            '/yjs/xy/', '/gs/college/'
        ]

        # 英文版/国际版特征（URL路径）
        self.english_path_patterns = [
            '/en/', '/english/', '/eng/', '/en-us/',
            '/international/', '/intl/', '/int/',
            '/abroad/', '/overseas/', '/global/',
            '/foreign/', '/study-in-china/',
            '_en/', '-en/', '/en_us/'
        ]

        # 留学生招生关键词
        self.international_keywords = [
            '留学生招生', '国际学生', 'International Students',
            '外国留学生', '来华留学', 'Study in China',
            'Admission for International', 'Foreign Students',
            '留学生', 'international admission'
        ]

        # 第三方网站黑名单
        self.third_party_domains = [
            'chsi.com.cn',      # 学信网
            'kaoyan.com',       # 考研网
            'yanzhao.net',      # 研招网(第三方)
            'chinakaoyan.com',  # 中国考研网
            'kaoyan365.cn',     # 考研365
            'eduei.com',        # 教育信息网
            'eol.cn',           # 中国教育在线
            'gaokao.com',       # 高考网
            'bysjy.com.cn',     # 北京高校毕业生就业信息网
        ]

        # 多校区院校名单（需要进行省份验证的学校）
        self.multi_campus_schools = [
            '中国地质大学',
            '中国石油大学',
            '中国矿业大学',
            '华北电力大学'
        ]

        # 省份变体映射（用于识别省份名称的不同写法）
        self.province_variants = {
            '北京': ['北京', '北京市', '京'],
            '上海': ['上海', '上海市', '沪'],
            '天津': ['天津', '天津市', '津'],
            '重庆': ['重庆', '重庆市', '渝'],
            '河北': ['河北', '河北省', '石家庄', '石家庄市', '冀'],
            '山西': ['山西', '山西省', '太原', '太原市', '晋'],
            '辽宁': ['辽宁', '辽宁省', '沈阳', '沈阳市', '辽'],
            '吉林': ['吉林', '吉林省', '长春', '长春市', '吉'],
            '黑龙江': ['黑龙江', '黑龙江省', '哈尔滨', '哈尔滨市', '黑'],
            '江苏': ['江苏', '江苏省', '南京', '南京市', '苏'],
            '浙江': ['浙江', '浙江省', '杭州', '杭州市', '浙'],
            '安徽': ['安徽', '安徽省', '合肥', '合肥市', '皖'],
            '福建': ['福建', '福建省', '福州', '福州市', '闽'],
            '江西': ['江西', '江西省', '南昌', '南昌市', '赣'],
            '山东': ['山东', '山东省', '济南', '济南市', '鲁'],
            '河南': ['河南', '河南省', '郑州', '郑州市', '豫'],
            '湖北': ['湖北', '湖北省', '武汉', '武汉市', '鄂'],
            '湖南': ['湖南', '湖南省', '长沙', '长沙市', '湘'],
            '广东': ['广东', '广东省', '广州', '广州市', '粤'],
            '海南': ['海南', '海南省', '海口', '海口市', '琼'],
            '四川': ['四川', '四川省', '成都', '成都市', '川', '蜀'],
            '贵州': ['贵州', '贵州省', '贵阳', '贵阳市', '贵', '黔'],
            '云南': ['云南', '云南省', '昆明', '昆明市', '云', '滇'],
            '陕西': ['陕西', '陕西省', '西安', '西安市', '陕', '秦'],
            '甘肃': ['甘肃', '甘肃省', '兰州', '兰州市', '甘', '陇'],
            '青海': ['青海', '青海省', '西宁', '西宁市', '青'],
            '台湾': ['台湾', '台湾省', '台北', '台北市', '台'],
            '内蒙古': ['内蒙古', '内蒙古自治区', '呼和浩特', '呼和浩特市', '蒙'],
            '广西': ['广西', '广西壮族自治区', '南宁', '南宁市', '桂'],
            '西藏': ['西藏', '西藏自治区', '拉萨', '拉萨市', '藏'],
            '宁夏': ['宁夏', '宁夏回族自治区', '银川', '银川市', '宁'],
            '新疆': ['新疆', '新疆维吾尔自治区', '乌鲁木齐', '乌鲁木齐市', '新'],
            '香港': ['香港', '香港特别行政区', '港'],
            '澳门': ['澳门', '澳门特别行政区', '澳']
        }

        # Playwright 初始化
        self.playwright = None
        self.browser = None
        self.context = None

    def _init_browser(self):
        """初始化浏览器"""
        # 检查是否已经成功初始化（检查 context 而不是 playwright）
        if self.context:
            return

        try:
            # 清理可能存在的部分初始化状态
            self._close_browser()

            # 初始化 Playwright
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,  # 无头模式
                args=['--disable-blink-features=AutomationControlled']  # 反反爬
            )
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
        except Exception as e:
            # 初始化失败时清理所有状态
            logger.error(f"浏览器初始化失败: {e}")
            self._close_browser()
            raise

    def _close_browser(self):
        """关闭浏览器"""
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            logger.warning(f"关闭 context 时出错: {e}")
        finally:
            self.context = None

        try:
            if self.browser:
                self.browser.close()
        except Exception as e:
            logger.warning(f"关闭 browser 时出错: {e}")
        finally:
            self.browser = None

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.warning(f"停止 playwright 时出错: {e}")
        finally:
            self.playwright = None

    def _random_delay(self, min_seconds=2, max_seconds=5):
        """随机延迟"""
        time.sleep(random.uniform(min_seconds, max_seconds))

    def _extract_school_identifier(self, school_name: str) -> List[str]:
        """
        从学校名称提取可能的域名标识
        返回可能的拼音/缩写列表
        """
        identifiers = []
        clean_name = school_name.replace('大学', '').replace('学院', '').replace('学校', '')
        return identifiers

    # ========== 必要条件1：校级研招网（非院级） ==========

    def check_not_college_level(self, url: str, college_name: str, html: str = None) -> Tuple[bool, str]:
        """
        检查是否是校级（非院级）
        返回: (是否通过, 原因)
        """
        # 1.1 URL路径检查
        url_lower = url.lower()
        for pattern in self.college_path_patterns:
            if pattern in url_lower:
                return False, f"URL包含学院路径特征: {pattern}"

        # 1.2 如果有HTML内容，进行深度检查
        if html and college_name:
            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 检查标题
                title = soup.title.string if soup.title else ""
                title = title.strip() if title else ""

                if college_name in title:
                    return False, f"标题包含学院名: {title}"

                # 检查正文中学院名出现频率
                for script in soup(['script', 'style']):
                    script.decompose()
                text_content = soup.get_text(separator=' ', strip=True)

                college_count = text_content.count(college_name)
                if college_count > 5:
                    return False, f"学院名在正文中出现{college_count}次，疑似学院页面"

            except Exception as e:
                logger.warning(f"解析HTML时出错: {e}")

        return True, "通过校级检查（非学院页面）"

    # ========== 必要条件2：中文研招网 ==========

    def check_is_chinese(self, url: str, html: str) -> Tuple[bool, str]:
        """
        检查是否是中文研招网（非英文/国际版）
        返回: (是否通过, 原因)

        判断逻辑：只要标题中有中文即可
        """
        if not html:
            return False, "无法获取网页内容，无法验证是否中文"

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 获取标题
            title = soup.title.string if soup.title else ""
            title = title.strip() if title else ""

            if not title:
                return False, "网页标题为空，无法判断语言"

            # 检查标题中是否包含中文字符
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', title))

            if chinese_chars > 0:
                return True, f"通过中文检查（标题包含{chinese_chars}个中文字符）"
            else:
                return False, f"标题中无中文字符: {title}"

        except Exception as e:
            logger.warning(f"中文检查时出错: {e}")
            return False, f"内容解析失败: {e}"

    # ========== 必要条件3：目标院校的研招网 ==========

    def check_is_target_school(self, url: str, school_name: str, html: str) -> Tuple[bool, str]:
        """
        检查是否是目标院校的研招网
        返回: (是否通过, 原因)

        判断逻辑：学校名在标题或正文中出现≥1次即可
        """
        if not html:
            return False, "无法获取网页内容，无法验证学校"

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 获取标题
            title = soup.title.string if soup.title else ""
            title = title.strip() if title else ""

            # 提取学校简称
            school_short = school_name.replace('大学', '').replace('学院', '')

            # 检查标题中是否包含学校名
            if school_name in title or school_short in title:
                return True, f"通过目标学校验证（标题包含学校名）: {title}"

            # 获取正文内容
            for script in soup(['script', 'style']):
                script.decompose()
            text_content = soup.get_text(separator=' ', strip=True)

            # 统计学校名在正文中出现次数
            school_count = text_content.count(school_name)

            # 正文中只要出现≥1次即可
            if school_count >= 1:
                return True, f"通过目标学校验证（正文中学校名出现{school_count}次）"
            else:
                return False, f"标题和正文中均未出现学校名称: {title}"

        except Exception as e:
            logger.warning(f"目标学校检查时出错: {e}")
            return False, f"内容解析失败: {e}"


    # ========== 多校区院校判断 ==========

    def is_multi_campus_school(self, school_name: str) -> bool:
        """
        判断是否是多校区院校
        返回: True/False
        """
        for multi_school in self.multi_campus_schools:
            if multi_school in school_name:
                return True
        return False

    # ========== 必要条件5：省份匹配（仅多校区院校） ==========

    def extract_footer(self, html: str) -> str:
        """
        从HTML中提取footer内容
        返回: footer文本
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 优先级1: <footer> 标签
            footer = soup.find('footer')
            if footer:
                return footer.get_text(separator=' ', strip=True)

            # 优先级2: class或id包含footer的div
            footer = soup.find('div', {'class': re.compile(r'footer', re.I)})
            if footer:
                return footer.get_text(separator=' ', strip=True)

            footer = soup.find('div', {'id': re.compile(r'footer', re.I)})
            if footer:
                return footer.get_text(separator=' ', strip=True)

            # 优先级3: class或id包含bottom的div
            footer = soup.find('div', {'class': re.compile(r'bottom', re.I)})
            if footer:
                return footer.get_text(separator=' ', strip=True)

            footer = soup.find('div', {'id': re.compile(r'bottom', re.I)})
            if footer:
                return footer.get_text(separator=' ', strip=True)

            # 优先级4: 提取页面最后1000个字符
            all_text = soup.get_text(separator=' ', strip=True)
            if len(all_text) > 1000:
                return all_text[-1000:]
            else:
                return all_text

        except Exception as e:
            logger.warning(f"提取footer时出错: {e}")
            return ""

    def extract_provinces_from_footer(self, footer_text: str) -> List[str]:
        """
        从footer文本中提取省份
        返回: 省份列表（去重）
        """
        found_provinces = []

        # 查找"地址："关键词后面的内容
        address_patterns = [
            r'地址[:：]\s*([^\n]{10,100})',
            r'地址[:：]\s*([^\n]{10,100})',
            r'Address[:：]\s*([^\n]{10,100})'
        ]

        address_texts = []
        for pattern in address_patterns:
            matches = re.findall(pattern, footer_text)
            address_texts.extend(matches)

        # 如果没找到地址关键词，就在整个footer中查找
        if not address_texts:
            address_texts = [footer_text]

        # 在地址文本中查找省份
        for address_text in address_texts:
            for province, variants in self.province_variants.items():
                for variant in variants:
                    # 排除单字省份简称（如"京"、"沪"），只在特定上下文中匹配
                    if len(variant) == 1:
                        # 单字省份简称需要在特定模式中出现，如"京ICP"不算，但"北京"要算
                        continue

                    if variant in address_text:
                        # 找到省份，添加到列表（使用标准省份名）
                        if province not in found_provinces:
                            found_provinces.append(province)
                        break  # 找到一个变体就够了

        return found_provinces

    def check_province_match(self, csv_province: str, html: str) -> Tuple[bool, str, str]:
        """
        检查省份是否匹配（仅多校区院校需要）
        返回: (是否确定, 判断结果, 原因)

        返回值说明：
        - (True, "是", reason): 省份匹配，确定是
        - (True, "否", reason): 省份不匹配，确定否
        - (False, "不确定", reason): 无法确定（多省份或提取失败）
        """
        # 提取footer
        footer_text = self.extract_footer(html)
        if not footer_text:
            return False, "不确定", "无法提取footer内容"

        # 从footer中提取省份
        extracted_provinces = self.extract_provinces_from_footer(footer_text)

        if not extracted_provinces:
            return False, "不确定", "无法从footer中提取省份信息"

        # 情况1：只提取到1个省份
        if len(extracted_provinces) == 1:
            if extracted_provinces[0] == csv_province:
                return True, "是", f"省份匹配：footer地址为{extracted_provinces[0]}"
            else:
                return True, "否", f"省份不符：期望{csv_province}，实际{extracted_provinces[0]}"

        # 情况2：提取到多个省份（≥2）
        else:
            if csv_province in extracted_provinces:
                provinces_str = '、'.join(extracted_provinces)
                return False, "不确定", f"多校区地址（{provinces_str}），包含{csv_province}，但无法确定主校区"
            else:
                provinces_str = '、'.join(extracted_provinces)
                return True, "否", f"省份不符：期望{csv_province}，footer为{provinces_str}"

    # ========== 必要条件4：官网（非第三方） ==========

    def check_is_official(self, url: str) -> Tuple[bool, str]:
        """
        检查是否是官网（非第三方）
        返回: (是否通过, 原因)
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 4.1 必须是.edu.cn域名
            if not domain.endswith('.edu.cn'):
                return False, f"非.edu.cn域名: {domain}"

            # 4.2 检查是否在第三方黑名单中
            for third_party in self.third_party_domains:
                if third_party in domain:
                    return False, f"第三方网站: {domain}"

        except Exception as e:
            return False, f"URL解析失败: {e}"

        return True, f"通过官网验证（{domain}）"

    # ========== 网页抓取（使用Playwright） ==========

    def fetch_webpage(self, url: str, max_retries=3) -> Tuple[str, int, str]:
        """
        使用Playwright获取网页内容
        返回: (HTML内容, 状态码, 最终URL)
        """
        final_url = url

        for attempt in range(max_retries):
            try:
                # 延迟
                if attempt > 0:
                    delay = 2 ** attempt + random.uniform(0, 2)
                    logger.info(f"重试 {attempt + 1}/{max_retries}，延迟 {delay:.1f}秒")
                    time.sleep(delay)
                else:
                    self._random_delay()

                # 初始化浏览器（如果还没有初始化）
                self._init_browser()

                # 创建新页面
                page = self.context.new_page()

                try:
                    # 访问页面，等待加载
                    response = page.goto(url, wait_until='domcontentloaded', timeout=30000)

                    # 获取最终URL（处理重定向）
                    final_url = page.url

                    # 等待一下，确保动态内容加载
                    page.wait_for_timeout(2000)

                    # 获取页面内容
                    html = page.content()

                    # 获取状态码
                    status_code = response.status if response else 200

                    page.close()

                    if status_code == 200:
                        return html, status_code, final_url
                    else:
                        logger.warning(f"HTTP {status_code}: {url}")

                except Exception as e:
                    logger.warning(f"页面访问失败 (尝试 {attempt + 1}/{max_retries}): {url}, 错误: {e}")
                finally:
                    try:
                        page.close()
                    except:
                        pass

            except Exception as e:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {url}, 错误: {e}")

        return "", 0, final_url

    # ========== 综合判断 ==========

    def strict_judge(self, url: str, school_name: str, college_name: str = '', province: str = '') -> Dict:
        """
        严格判断（必要条件法）
        返回: {
            'url': str,
            'is_graduate_site': str,  # '是', '否', '不确定'
            'failed_condition': str,   # 未通过的条件
            'reasons': str             # 详细原因
        }
        """
        logger.info(f"正在检查: {school_name} - {url}")

        all_checks = []

        # ===== 必要条件4：官网（最先检查，避免访问第三方网站）=====
        is_official, reason = self.check_is_official(url)
        all_checks.append(f"[条件4-官网] {reason}")
        if not is_official:
            return {
                'url': url,
                'is_graduate_site': '否',
                'failed_condition': '条件4：必须是官网',
                'reasons': '; '.join(all_checks)
            }

        # ===== 必要条件1（URL层面）：非院级 =====
        is_not_college, reason = self.check_not_college_level(url, college_name, None)
        all_checks.append(f"[条件1-URL层面] {reason}")
        if not is_not_college:
            return {
                'url': url,
                'is_graduate_site': '否',
                'failed_condition': '条件1：必须是校级（URL包含学院特征）',
                'reasons': '; '.join(all_checks)
            }

        # ===== 抓取网页 =====
        html, status_code, final_url = self.fetch_webpage(url)

        if status_code != 200:
            all_checks.append(f"[网页访问] 失败 (状态码: {status_code})")
            return {
                'url': url,
                'is_graduate_site': '不确定',
                'failed_condition': '无法访问网页',
                'reasons': '; '.join(all_checks)
            }

        all_checks.append(f"[网页访问] 成功")

        # 检查是否发生跳转
        if final_url != url:
            all_checks.append(f"[URL跳转] {url} -> {final_url}")
            # 重新检查跳转后的URL是否是官网
            is_official_after, reason_after = self.check_is_official(final_url)
            if not is_official_after:
                return {
                    'url': url,
                    'is_graduate_site': '否',
                    'failed_condition': '条件4：跳转后非官网',
                    'reasons': '; '.join(all_checks) + f'; {reason_after}'
                }

        # ===== 必要条件2：中文 =====
        is_chinese, reason = self.check_is_chinese(final_url, html)
        all_checks.append(f"[条件2-中文] {reason}")
        if not is_chinese:
            return {
                'url': url,
                'is_graduate_site': '否',
                'failed_condition': '条件2：必须是中文研招网',
                'reasons': '; '.join(all_checks)
            }

        # ===== 必要条件3：目标院校 =====
        is_target, reason = self.check_is_target_school(final_url, school_name, html)
        all_checks.append(f"[条件3-目标学校] {reason}")
        if not is_target:
            return {
                'url': url,
                'is_graduate_site': '否',
                'failed_condition': '条件3：非目标院校',
                'reasons': '; '.join(all_checks)
            }

        # ===== 必要条件1（内容层面）：非院级 =====
        is_not_college_content, reason = self.check_not_college_level(final_url, college_name, html)
        all_checks.append(f"[条件1-内容层面] {reason}")
        if not is_not_college_content:
            return {
                'url': url,
                'is_graduate_site': '否',
                'failed_condition': '条件1：必须是校级（内容偏向学院）',
                'reasons': '; '.join(all_checks)
            }

        # ===== 判断是否是多校区院校 =====
        is_multi_campus = self.is_multi_campus_school(school_name)

        if is_multi_campus and province:
            # 多校区院校，需要进行省份验证（条件5）
            all_checks.append(f"[多校区院校] {school_name}需要省份验证")

            is_certain, result, reason = self.check_province_match(province, html)
            all_checks.append(f"[条件5-省份匹配] {reason}")

            if is_certain:
                # 确定的结果（是/否）
                if result == "是":
                    logger.info(f"判断结果: 是 - 通过所有5项必要条件（含省份验证）")
                    return {
                        'url': url,
                        'is_graduate_site': '是',
                        'failed_condition': '',
                        'reasons': '; '.join(all_checks)
                    }
                else:  # result == "否"
                    return {
                        'url': url,
                        'is_graduate_site': '否',
                        'failed_condition': '条件5：省份不匹配',
                        'reasons': '; '.join(all_checks)
                    }
            else:
                # 不确定的结果
                return {
                    'url': url,
                    'is_graduate_site': '不确定',
                    'failed_condition': '条件5：无法确定省份',
                    'reasons': '; '.join(all_checks)
                }
        else:
            # 非多校区院校，或者没有提供省份信息，跳过省份验证
            if is_multi_campus:
                all_checks.append(f"[多校区院校] {school_name}，但未提供省份信息，跳过省份验证")
            else:
                all_checks.append(f"[非多校区院校] 跳过省份验证")

        # ===== 所有条件都满足 =====
        logger.info(f"判断结果: 是 - 通过所有必要条件")
        return {
            'url': url,
            'is_graduate_site': '是',
            'failed_condition': '',
            'reasons': '; '.join(all_checks)
        }


def main():
    """主函数"""
    # 输入文件路径
    input_file = '示例文件.csv'
    # 输出文件路径
    output_file = '判断结果.csv'

    logger.info("="*60)
    logger.info("研招网官网严格判断程序启动（必要条件法 + Playwright）")
    logger.info("="*60)

    # 读取CSV
    try:
        df = pd.read_csv(input_file, encoding='utf-8-sig')

        # 检查是否有表头
        if '省份' not in df.columns:
            df.columns = ['省份', '学校', '学院', 'URL']

        logger.info(f"读取到 {len(df)} 条记录")
    except Exception as e:
        logger.error(f"读取CSV文件失败: {e}")
        return

    # 初始化检查器
    checker = StrictGraduateChecker()

    # 结果列表
    results = []

    try:
        # 逐条检查
        for idx, row in df.iterrows():
            province = row['省份']
            school = row['学校']
            college = row['学院']
            url = row['URL']

            logger.info(f"\n{'='*60}")
            logger.info(f"[{idx+1}/{len(df)}] {province} - {school} - {college}")
            logger.info(f"URL: {url}")

            # 执行严格判断（传递省份参数）
            result = checker.strict_judge(url, school, college, province)

            # 保存结果
            results.append({
                '省份': province,
                '学校': school,
                '学院': college,
                'URL': url,
                '判断结果': result['is_graduate_site'],
                '未通过的条件': result['failed_condition'],
                '详细原因': result['reasons']
            })

            logger.info(f"判断结果: {result['is_graduate_site']}")
            if result['failed_condition']:
                logger.info(f"失败原因: {result['failed_condition']}")

    finally:
        # 确保关闭浏览器
        checker._close_browser()

    # 保存结果
    result_df = pd.DataFrame(results)
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    logger.info(f"\n{'='*60}")
    logger.info(f"判断完成！结果已保存至: {output_file}")
    logger.info(f"{'='*60}")

    # 统计结果
    stats = result_df['判断结果'].value_counts()
    logger.info("\n【统计结果】")
    for status, count in stats.items():
        logger.info(f"  {status}: {count} 条 ({count/len(result_df)*100:.1f}%)")

    # 统计失败原因
    failed_df = result_df[result_df['判断结果'] == '否']
    if len(failed_df) > 0:
        logger.info("\n【失败原因统计】")
        failed_stats = failed_df['未通过的条件'].value_counts()
        for condition, count in failed_stats.items():
            logger.info(f"  {condition}: {count} 条")


if __name__ == '__main__':
    main()
