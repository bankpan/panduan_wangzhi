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
        """
        # 2.1 URL检查
        url_lower = url.lower()
        for pattern in self.english_path_patterns:
            if pattern in url_lower:
                return False, f"URL包含英文版特征: {pattern}"

        if not html:
            return True, "无HTML内容，仅通过URL检查"

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 2.2 标题检查
            title = soup.title.string if soup.title else ""
            title = title.strip() if title else ""

            # 检查标题是否是纯英文
            if title:
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', title))
                english_chars = len(re.findall(r'[a-zA-Z]', title))

                if english_chars > chinese_chars and any(word in title.lower() for word in ['graduate', 'admission', 'international', 'students', 'university']):
                    return False, f"标题疑似英文版: {title}"

            # 2.3 留学生招生检查
            text_content = soup.get_text(separator=' ', strip=True)
            for keyword in self.international_keywords:
                if keyword in title or text_content[:500].count(keyword) >= 2:
                    return False, f"疑似留学生/国际招生页面，包含关键词: {keyword}"

            # 2.4 中文内容占比检查
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text_content))
            total_chars = len(re.findall(r'[\u4e00-\u9fff\w]', text_content))

            if total_chars > 0:
                chinese_ratio = chinese_chars / total_chars
                if chinese_ratio < 0.6:
                    return False, f"中文内容占比过低: {chinese_ratio:.1%}"

        except Exception as e:
            logger.warning(f"中文检查时出错: {e}")

        return True, "通过中文检查"

    # ========== 必要条件3：目标院校的研招网 ==========

    def check_is_target_school(self, url: str, school_name: str, html: str) -> Tuple[bool, str]:
        """
        检查是否是目标院校的研招网
        返回: (是否通过, 原因)
        
        判断逻辑（方案1 - 放宽标题要求）：
        1. 优先检查正文中学校名出现次数（主要依据）
        2. 如果正文出现≥3次，直接通过
        3. 如果正文出现<3次，结合标题判断
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

            # 获取正文内容
            for script in soup(['script', 'style']):
                script.decompose()
            text_content = soup.get_text(separator=' ', strip=True)

            # 统计学校名在正文中出现次数
            school_count = text_content.count(school_name)

            # 核心判断逻辑
            # 情况1：正文中学校名出现≥3次 → 直接通过（不管标题）
            if school_count >= 3:
                return True, f"通过目标学校验证（正文中学校名出现{school_count}次）"

            # 情况2：正文中学校名出现<3次 → 需要结合标题判断
            title_has_school = school_name in title or school_short in title
            
            if school_count >= 1 and title_has_school:
                # 正文至少出现1次，且标题也有学校名 → 通过
                return True, f"通过目标学校验证（标题+正文共同验证，正文出现{school_count}次）"
            elif title_has_school and school_count == 0:
                # 只有标题有，正文一次都没有 → 不通过
                return False, f"标题包含学校名，但正文中未出现学校名称"
            else:
                # 其他情况：正文太少且标题也没有 → 不通过
                return False, f"学校名称在正文中仅出现{school_count}次，且标题未包含学校名: {title}"

        except Exception as e:
            logger.warning(f"目标学校检查时出错: {e}")
            return False, f"内容解析失败: {e}"


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

    def strict_judge(self, url: str, school_name: str, college_name: str = '') -> Dict:
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

        # ===== 所有条件都满足 =====
        logger.info(f"判断结果: 是 - 通过所有4项必要条件")
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

            # 执行严格判断
            result = checker.strict_judge(url, school, college)

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
