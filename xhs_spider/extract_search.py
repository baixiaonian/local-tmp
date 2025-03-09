import asyncio
import json
from datetime import datetime
import random
import base64
import io
import os
from DrissionPage import ChromiumPage
from DataRecorder import Recorder
import pandas as pd
from tqdm import tqdm
import time
import math
from urllib.parse import quote
import openpyxl
import sys
import logging

class XHSSearchCrawler:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
        ]
        
    async def init(self):
        """初始化浏览器环境"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--start-maximized'
            ]
        )
        self.context = await self.browser.new_context(
            viewport={"width": random.randint(1200, 1920), "height": random.randint(800, 1080)},
            user_agent=random.choice(self.user_agents),
            locale="zh-CN",
            timezone_id="Asia/Shanghai"
        )
        await self.context.add_init_script(path="libs/stealth.min.js")
        self.page = await self.context.new_page()
        
    async def check_login_state(self):
        """检查登录状态"""
        try:
            # 先确保在小红书页面
            current_url = self.page.url
            if not current_url.startswith("https://www.xiaohongshu.com"):
                print("当前不在小红书页面，正在跳转...")
                await self.page.goto("https://www.xiaohongshu.com/explore", timeout=30000)
                await asyncio.sleep(3)

            # 更严格的登录检查
            checks = [
                ('xpath=//div[contains(@class,"login-modal")]', "未登录弹窗"),  # 如果存在登录弹窗，说明未登录
                ('xpath=//div[contains(@class,"avatar-img")]', "头像"),
                ('xpath=//div[contains(@class,"user-name")]', "用户名")
            ]
            
            # 检查是否存在登录弹窗（未登录状态）
            login_modal = await self.page.query_selector(checks[0][0])
            if login_modal:
                print("检测到登录弹窗，需要登录")
                return False

            # 检查登录状态标志
            login_indicators = 0
            for selector, desc in checks[1:]:
                if await self.page.query_selector(selector):
                    print(f"登录验证：检测到 {desc}")
                    login_indicators += 1

            # 至少要有两个登录标志才认为是已登录状态
            is_logged_in = login_indicators >= 2
            if not is_logged_in:
                print("登录状态检查：未检测到足够的登录标志")
            
            return is_logged_in

        except Exception as e:
            print(f"登录状态检查出错：{str(e)}")
            return False

    async def login(self, max_retry=3):
        """修改后的登录流程"""
        try:
            await self.page.goto("https://www.xiaohongshu.com/explore", timeout=60000)
            
            if await self.check_login_state():
                print("当前已登录")
                return True
            
            # 触发登录弹窗
            login_btn = await self.page.wait_for_selector(
                'xpath=//button[contains(text(),"登录")]',
                timeout=10000
            )
            await login_btn.click()
            
            # 获取二维码
            qr_img = await self.page.wait_for_selector(
                'xpath=//div[contains(@class,"qrcode-container")]//img',
                timeout=15000
            )
            qr_src = await qr_img.get_attribute("src")
            
            # 显示二维码
            if qr_src:
                base64_img = qr_src.split("base64,")[-1]
                if not os.environ.get('DISPLAY'):
                    print(f"BASE64二维码:\n{base64_img[:100]}...")
                else:
                    img = Image.open(io.BytesIO(base64.b64decode(base64_img)))
                    img.show()
                print("请扫码登录（60秒内有效）...")

                # 等待登录成功
                await self.page.wait_for_selector(
                    'xpath=//input[@placeholder="搜索"]',
                    timeout=60000
                )
                print("登录成功！")
                await asyncio.sleep(3)
                return True
                
        except Exception as e:
            print(f"登录失败：{str(e)}")
            await self.page.screenshot(path=f"login_fail_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
            return False

    async def safe_click(self, selector, timeout=15000, max_retry=3):
        """带重试的安全点击"""
        for _ in range(max_retry):
            try:
                element = await self.page.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=timeout
                )
                await element.scroll_into_view_if_needed()
                await element.click(delay=random.uniform(100, 300))
                return True
            except:
                await asyncio.sleep(1)
        return False

    async def search(self, keyword: str, max_pages: int = 1) -> list:
        """修复版搜索功能"""
        try:
            # 定位搜索入口
            search_selectors = [
                'xpath=//input[@placeholder="搜索"]',
                'xpath=//div[contains(@class,"search-bar")]',
                'xpath=//button[contains(@class,"search-btn")]'
            ]
            
            for selector in search_selectors:
                if await self.safe_click(selector, timeout=10000):
                    break
            else:
                raise Exception("未找到搜索入口")

            # 输入关键词
            input_selector = 'xpath=//input[@type="search" and @placeholder="搜索"]'
            await self.page.wait_for_selector(input_selector, state="visible", timeout=15000)
            await self.page.type(
                input_selector,
                keyword,
                delay=random.uniform(50, 150)  # 模拟真人输入
            )
            await self.page.keyboard.press("Enter")
            
            # 等待结果加载
            await self.page.wait_for_selector(
                'xpath=//div[contains(@class,"note-item")]',
                timeout=20000
            )
            print("已进入搜索结果页")

            # 滚动加载
            results = []
            last_count = 0
            for _ in range(max_pages):
                # 动态滚动
                for _ in range(3):
                    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(random.uniform(2.0, 3.5))
                    
                # 提取数据
                notes = await self.page.query_selector_all(
                    'xpath=//div[contains(@class,"note-item")]'
                )
                print(f"当前页获取到 {len(notes)} 条结果")
                
                for note in notes:
                    try:
                        title = await note.query_selector("xpath=.//h3")
                        link = await note.query_selector("xpath=.//a[contains(@href,'/explore/')]")
                        result = {
                            "title": (await title.text_content()).strip() if title else "",
                            "url": f"https://www.xiaohongshu.com{await link.get_attribute('href')}" if link else "",
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        results.append(result)
                    except:
                        continue
                
                # 页数控制
                if len(notes) <= last_count:
                    break
                last_count = len(notes)
                await asyncio.sleep(random.uniform(1.5, 2.5))

            return results
            
        except Exception as e:
            print(f"搜索出错：{str(e)}")
            await self.page.screenshot(path=f"search_error_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
            return []

    async def close(self):
        """关闭资源"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

def countdown(n):
    """倒计时函数"""
    for i in range(n, 0, -1):
        print(f'\r倒计时{i}秒', end='')
        time.sleep(1)
    print('\r倒计时结束')

def search_keyword(page, keyword):
    """搜索关键词"""
    try:
        # 直接访问搜索结果页面
        encoded_keyword = quote(keyword)  # 使用 urllib.parse.quote 进行编码
        
        # 构造完整的搜索URL
        search_url = (
            f'https://www.xiaohongshu.com/search_result?'
            f'keyword={encoded_keyword}&'
            f'source=web_search_result_notes&'
            f'type=51'
        )
        print(f"正在跳转到搜索页面: {search_url}")
        page.get(search_url)
        time.sleep(5)  # 增加等待时间
        
        # 验证搜索结果页面
        if 'search_result' in page.url:
            print("成功进入搜索结果页面")
            
            # 等待搜索结果加载
            selectors = [
                'xpath://div[contains(@class, "note-item")]',  # 通用笔记项
                'xpath://div[contains(@class, "feeds-page")]//a[contains(@href, "/explore/")]',  # 笔记链接
                'xpath://div[contains(@class, "content")]//a[contains(@href, "/explore/")]',  # 备用笔记链接
                'xpath://div[contains(@class, "search-container")]//div[contains(@class, "note-item")]'  # 搜索容器
            ]
            
            # 增加重试机制
            max_retries = 3
            for _ in range(max_retries):
                for selector in selectors:
                    try:
                        elements = page.eles(selector, timeout=5)
                        if elements:
                            print(f"找到 {len(elements)} 个搜索结果")
                            return True
                    except:
                        continue
                
                print("未找到结果，等待页面加载...")
                time.sleep(2)
            
            # 如果多次重试后仍未找到结果，尝试执行JavaScript检查
            try:
                note_count = page.run_js("""
                    return document.querySelectorAll('div[class*="note-item"], a[href*="/explore/"]').length;
                """)
                if note_count > 0:
                    print(f"通过JavaScript检测到 {note_count} 个结果")
                    return True
            except:
                pass
            
            print("未检测到搜索结果")
            return False
            
        else:
            print("未能进入搜索结果页面")
            return False
            
    except Exception as e:
        print(f"搜索失败：{str(e)}")
        return False

def check_login_status(page):
    """检查登录状态"""
    try:
        # 等待页面加载
        time.sleep(3)
        
        # 多重检查登录状态
        checks = [
            # 检查登录弹窗是否存在（未登录标志）
            not page.ele('xpath://div[contains(@class,"login-modal")]', timeout=1),
            # 检查头像是否存在
            page.ele('xpath://div[contains(@class,"avatar")]', timeout=1) is not None,
            # 检查用户名是否存在
            page.ele('xpath://div[contains(@class,"user-name")]', timeout=1) is not None
        ]
        
        # 至少需要两个条件满足才认为是已登录
        login_status = sum(checks) >= 2
        
        if login_status:
            print("登录状态检查：已登录")
        else:
            print("登录状态检查：未登录")
            
        return login_status
        
    except Exception as e:
        print(f"登录状态检查出错: {str(e)}")
        return False

def get_search_results(page):
    """获取搜索结果信息"""
    results = []
    try:
        # 等待页面加载
        time.sleep(3)
        
        # 使用更精确的JavaScript选择器获取搜索结果
        script = """
        return Array.from(document.querySelectorAll('.feeds-page .note-item')).map(item => {
            // 获取笔记链接和ID
            const link = item.querySelector('a[href*="/explore/"]');
            const href = link ? link.getAttribute('href') : '';
            
            // 获取标题
            const title = item.querySelector('.title');
            
            // 获取作者信息
            const authorElement = item.querySelector('.author');
            const authorLink = authorElement ? authorElement.closest('a[href*="/user/profile/"]') : null;
            
            // 获取点赞数
            const likeElement = item.querySelector('.like-wrapper .count, .interaction-info .count');
            
            // 检查是否为视频
            const isVideo = item.querySelector('.play-icon') !== null;
            
            return {
                '标题': title ? title.textContent.trim() : '',
                '作者': authorElement ? authorElement.textContent.trim() : '',
                '笔记类型': isVideo ? '视频' : '图文',
                '点赞数': likeElement ? likeElement.textContent.trim() : '0',
                '笔记链接': href ? 'https://www.xiaohongshu.com' + href : '',
                '作者主页': authorLink ? 'https://www.xiaohongshu.com' + authorLink.getAttribute('href') : ''
            };
        });
        """
        
        items = page.run_js(script)
        
        if not items:
            print("未通过主方法获取到结果，尝试备用方法...")
            # 备用方法：使用更宽松的选择器
            backup_script = """
            return Array.from(document.querySelectorAll('div[class*="note-item"]')).map(item => {
                const link = item.querySelector('a');
                const title = item.querySelector('div[class*="title"]');
                const author = item.querySelector('div[class*="author"]');
                const authorLink = author ? author.closest('a') : null;
                const likeCount = item.querySelector('span[class*="count"]');
                const isVideo = item.querySelector('div[class*="play"]') !== null;
                
                return {
                    '标题': title ? title.textContent.trim() : '',
                    '作者': author ? author.textContent.trim() : '',
                    '笔记类型': isVideo ? '视频' : '图文',
                    '点赞数': likeCount ? likeCount.textContent.trim() : '0',
                    '笔记链接': link ? 'https://www.xiaohongshu.com' + link.getAttribute('href') : '',
                    '作者主页': authorLink ? 'https://www.xiaohongshu.com' + authorLink.getAttribute('href') : ''
                };
            });
            """
            items = page.run_js(backup_script)
        
        # 处理结果
        for item in items:
            if item['笔记链接'] and item['标题']:  # 只添加有效的结果
                # 清理数据
                item['标题'] = item['标题'].strip()
                item['作者'] = item['作者'].strip()
                item['点赞数'] = item['点赞数'].strip()
                
                # 验证链接格式
                if '/explore/' in item['笔记链接']:
                    results.append(item)
                    print(f"获取到笔记: {item['标题'][:30]}... | 作者: {item['作者']} | 点赞: {item['点赞数']}")
        
        if results:
            print(f"本页共获取到 {len(results)} 条有效结果")
        else:
            print("本页未获取到有效结果，可能是页面结构发生变化")
            # 保存页面源码以供调试
            debug_file = f'debug_page_{time.strftime("%Y%m%d_%H%M%S")}.html'
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(page.html)
            print(f"已保存页面源码到 {debug_file}")
            
    except Exception as e:
        print(f"获取搜索结果出错: {str(e)}")
        # 保存错误现场
        try:
            error_file = f'error_page_{time.strftime("%Y%m%d_%H%M%S")}.html'
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(page.html)
            print(f"已保存错误页面到 {error_file}")
        except:
            pass
        
    return results

def page_scroll_down(page):
    """页面向下滚动"""
    print("********下滑页面********")
    
    script = """
    window.scrollTo({
        top: document.documentElement.scrollHeight,
        behavior: 'smooth'
    });
    """
    page.run_js(script)
    time.sleep(3)

def process_excel(file_path, keyword):
    """处理Excel文件"""
    try:
        df = pd.read_excel(file_path)
        print(f"获取{df.shape[0]}条搜索结果（含重复）")
        
        # 数据处理
        df = df.drop_duplicates()
        
        # 将点赞数转换为数值类型并处理"万"单位
        def convert_likes(like_str):
            try:
                if isinstance(like_str, str):
                    if '万' in like_str:
                        return float(like_str.replace('万', '')) * 10000
                    return float(like_str)
                return float(like_str)
            except:
                return 0
        
        # 转换点赞数并排序
        df['点赞数'] = df['点赞数'].apply(convert_likes)
        df = df.sort_values(by='点赞数', ascending=False)
        
        # 将点赞数重新格式化为易读格式
        def format_likes(num):
            if num >= 10000:
                return f"{num/10000:.1f}万"
            return str(int(num))
        
        df['点赞数'] = df['点赞数'].apply(format_likes)
        
        # 生成新文件名
        timestamp = time.strftime("%H%M%S")
        final_file_path = f"小红书搜索结果-{keyword}-{df.shape[0]}条-{timestamp}.xlsx"
        
        try:
            # 调整列的顺序
            columns_order = ['标题', '作者', '笔记类型', '点赞数', '笔记链接', '作者主页']
            df = df[columns_order]
            
            df.to_excel(final_file_path, index=False)
            
            # 调整Excel列宽
            wb = openpyxl.load_workbook(final_file_path)
            ws = wb.active
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                ws.column_dimensions[column].width = max_length + 2
            wb.save(final_file_path)
            
        except PermissionError:
            random_suffix = random.randint(1, 1000)
            final_file_path = f"小红书搜索结果-{keyword}-{df.shape[0]}条-{timestamp}-{random_suffix}.xlsx"
            df.to_excel(final_file_path, index=False)
        
        # 打印排序后的前5条结果
        print("\n排序后的前5条结果：")
        for _, row in df.head().iterrows():
            print(f"标题: {row['标题'][:30]}... "
                  f"作者: {row['作者']} "
                  f"点赞数: {row['点赞数']}")
        
        print(f"\n数据已保存到：{final_file_path}")
        return final_file_path
        
    except Exception as e:
        print(f"处理Excel文件时出错: {str(e)}")
        return None

def main(keyword=None, pages=1):
    try:
        # 创建一个安全的输出函数
        def safe_print(message):
            try:
                if hasattr(sys.stdout, 'write'):
                    sys.stdout.write(f"{message}\n")
                    if hasattr(sys.stdout, 'flush'):
                        sys.stdout.flush()
            except:
                pass
            # 同时输出到日志文件
            logging.info(message)

        # 登录
        safe_print("正在初始化浏览器...")
        page = sign_in()
        if not page:
            safe_print("登录失败，程序退出")
            return
            
        # 使用传入的关键词，不再提示输入
        if not keyword:
            keyword = input("请输入要搜索的关键词：")
            
        # 使用传入的页数，不再提示输入    
        if not pages:
            pages = int(input("请输入要爬取的页数："))
        
        # 初始化结果列表
        all_results = []
        
        # 执行搜索
        if search_keyword(page, keyword):
            # 爬取搜索结果
            for i in range(pages):  # 移除tqdm
                safe_print(f"正在获取第 {i+1}/{pages} 页")
                results = get_search_results(page)
                if results:
                    safe_print(f"第 {i+1} 页获取到 {len(results)} 条结果")
                    all_results.extend(results)
                else:
                    safe_print(f"第 {i+1} 页没有获取到新结果")
                
                # 如果不是最后一页，则滚动加载下一页
                if i < pages - 1:
                    page_scroll_down(page)
                    time.sleep(3)  # 等待新内容加载
            
            # 保存数据到Excel
            if all_results:
                safe_print(f"\n总共获取到 {len(all_results)} 条结果")
                
                # 生成文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f'小红书搜索结果_{keyword}_{len(all_results)}条_{timestamp}.xlsx'
                
                try:
                    # 转换为DataFrame并处理数据
                    df = pd.DataFrame(all_results)
                    df = df.drop_duplicates()
                    df = df.drop_duplicates(subset=['标题', '笔记链接'])
                    
                    # 处理点赞数并排序
                    def convert_likes(like_str):
                        try:
                            if isinstance(like_str, str):
                                if '万' in like_str:
                                    return float(like_str.replace('万', '')) * 10000
                                return float(like_str)
                            return float(like_str)
                        except:
                            return 0
                    
                    df['点赞数值'] = df['点赞数'].apply(convert_likes)
                    df = df.sort_values(by='点赞数值', ascending=False)
                    df = df.drop('点赞数值', axis=1)
                    
                    # 保存文件
                    save_path = save_excel(df, filename)
                    safe_print(f"数据已成功保存到：{save_path}")
                    
                    # 显示统计信息
                    safe_print("\n数据统计：")
                    safe_print(f"原始数据条数：{len(all_results)}")
                    safe_print(f"去重后条数：{len(df)}")
                    safe_print("\n排序后的前5条结果：")
                    for _, row in df.head().iterrows():
                        safe_print(f"标题: {row['标题'][:30]}... 点赞数: {row['点赞数']}")
                    
                except Exception as e:
                    safe_print(f"保存Excel文件时出错: {str(e)}")
                    backup_filename = f'小红书搜索结果_{keyword}_{int(time.time())}.xlsx'
                    backup_path = save_excel(df, backup_filename)
                    safe_print(f"数据已保存到备用文件：{backup_path}")
            else:
                safe_print("没有找到任何搜索结果")
                
    except Exception as e:
        error_msg = f"程序执行出错: {str(e)}"
        logging.error(error_msg, exc_info=True)
        try:
            if hasattr(sys.stdout, 'write'):
                sys.stdout.write(f"{error_msg}\n")
        except:
            pass
    finally:
        if 'page' in locals():
            try:
                page.quit()
            except:
                pass

def sign_in():
    """登录小红书"""
    try:
        print("初始化浏览器...")
        page = ChromiumPage()
        
        # 访问小红书
        print("访问小红书...")
        page.get('https://www.xiaohongshu.com/explore')
        time.sleep(3)
        
        # 检查登录状态
        print("检查登录状态...")
        if check_login_status(page):
            print("已经登录")
            return page
            
        # 等待用户扫码登录
        print("请扫码登录")
        countdown(30)
        
        # 多次检查登录状态
        for i in range(3):
            if check_login_status(page):
                print("登录成功")
                return page
            time.sleep(3)
            
        print("登录失败")
        return None
            
    except Exception as e:
        print(f"登录过程出错: {str(e)}")
        return None

def get_executable_path():
    """获取可执行文件路径"""
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe运行
        return os.path.dirname(sys.executable)
    else:
        # 如果是python脚本运行
        return os.path.dirname(os.path.abspath(__file__))

# 在保存文件的地方使用这个路径
def save_excel(df, filename):
    """保存Excel文件"""
    save_path = os.path.join(get_executable_path(), filename)
    try:
        df.to_excel(save_path, index=False)
        print(f"数据已保存到：{save_path}")
        return save_path
    except Exception as e:
        print(f"保存文件出错: {str(e)}")
        # 尝试使用备用文件名
        backup_filename = f'数据_{int(time.time())}.xlsx'
        backup_path = os.path.join(get_executable_path(), backup_filename)
        df.to_excel(backup_path, index=False)
        print(f"数据已保存到备用文件：{backup_path}")
        return backup_path

if __name__ == '__main__':
    main()