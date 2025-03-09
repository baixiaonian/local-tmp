from DrissionPage import ChromiumPage
from DataRecorder import Recorder
import pandas as pd
from tqdm import tqdm
import time
import random
import re
import openpyxl
import os
import math
import sys
import logging

def countdown(n):
    """倒计时函数"""
    for i in range(n, 0, -1):
        print(f'\r倒计时{i}秒', end='')
        time.sleep(1)
    print('\r倒计时结束')

def sign_in():
    """登录小红书"""
    sign_in_page = ChromiumPage()
    sign_in_page.get('https://www.xiaohongshu.com')
    
    # 检查是否已登录
    try:
        # 尝试找登录按钮，如果找不到说明已登录
        if not sign_in_page.ele('.login-button', timeout=3):
            print("已检测到登录状态")
            return
    except:
        print("已检测到登录状态")
        return
        
    print("请扫码登录")
    countdown(30)

def open_author_page(url):
    """打开作者主页"""
    global page, user_name
    page = ChromiumPage()
    page.get(url)
    page.set.window.max()
    
    # 获取作者信息
    user = page.ele('.info')
    user_name = user.ele('.user-name', timeout=0).text
    return user_name

def get_note_info():
    """获取页面笔记信息"""
    notes = []
    
    try:
        # 等待页面加载完成
        time.sleep(2)
        
        # 获取所有笔记元素的基本信息
        script = """
        return Array.from(document.querySelectorAll('.note-item')).map(item => {
            const link = item.querySelector('a');
            const title = item.querySelector('.title');
            const count = item.querySelector('.count');
            const isVideo = item.querySelector('.play-icon') !== null;
            
            return {
                href: link ? link.getAttribute('href') : '',
                title: title ? title.textContent : '',
                like: count ? count.textContent : '',
                type: isVideo ? '视频' : '图文'
            };
        });
        """
        items = page.run_js(script)
        
        # 处理每个笔记
        for item in items:
            if not item['href']:
                continue
                
            # 直接构建完整URL
            note_link = f"https://www.xiaohongshu.com{item['href']}"
            
            note = {
                '作者': user_name,
                '笔记类型': item['type'],
                '标题': item['title'],
                '点赞数': item['like'],
                '笔记链接': note_link
            }
            notes.append(note)
            print(f"成功获取笔记: {item['title']} - {note_link}")
            
    except Exception as e:
        print(f"获取笔记信息出错: {str(e)}")
    
    return notes

def page_scroll_down():
    """改进的页面向下滚动"""
    print("********下滑页面********")
    
    try:
        # 使用多种滚动方式
        scroll_methods = [
            # 方法1: 使用JavaScript smooth scroll
            """
            window.scrollTo({
                top: document.documentElement.scrollHeight,
                behavior: 'smooth'
            });
            """,
            
            # 方法2: 使用简单的scrollTo
            """
            window.scrollTo(0, document.documentElement.scrollHeight);
            """,
            
            # 方法3: 使用scrollBy逐步滚动
            """
            let height = document.documentElement.clientHeight;
            window.scrollBy(0, height);
            """
        ]
        
        # 尝试不同的滚动方法
        for scroll_script in scroll_methods:
            try:
                page.run_js(scroll_script)
                time.sleep(1)
                
                # 检查是否成功滚动
                new_height = page.run_js("return window.pageYOffset;")
                if new_height > 0:
                    break
            except:
                continue
                
        # 等待内容加载
        time.sleep(2)
        
        # 检查是否需要点击"加载更多"按钮
        load_more_selectors = [
            '//div[contains(text(), "加载更多")]',
            '//button[contains(text(), "加载更多")]',
            '//span[contains(text(), "加载更多")]'
        ]
        
        for selector in load_more_selectors:
            try:
                load_more = page.ele(f'xpath:{selector}', timeout=1)
                if load_more:
                    load_more.click()
                    time.sleep(2)
                    break
            except:
                continue
                
    except Exception as e:
        print(f"页面滚动出错: {str(e)}")
        # 出错时使用备用滚动方法
        try:
            page.run_js("window.scrollTo(0, document.documentElement.scrollHeight);")
            time.sleep(2)
        except:
            pass

def crawler(times, recorder):
    """爬取数据"""
    def safe_print(message):
        try:
            if hasattr(sys.stdout, 'write'):
                sys.stdout.write(f"{message}\n")
                if hasattr(sys.stdout, 'flush'):
                    sys.stdout.flush()
        except:
            pass
        logging.info(message)
        
    for i in range(1, times + 1):  # 移除tqdm
        safe_print(f"正在获取第 {i}/{times} 页")
        notes = get_note_info()
        if notes:  # 只有在成功获取到笔记时才记录
            recorder.add_data(notes)
            safe_print(f"第 {i} 页获取到 {len(notes)} 条笔记")
        else:
            safe_print(f"第 {i} 页未获取到笔记")
        page_scroll_down()

def convert_likes_to_number(like_str):
    """将点赞数文本转换为数字"""
    try:
        if '万' in like_str:
            return int(float(like_str.replace('万', '')) * 10000)
        return int(like_str)
    except:
        return 0

def process_excel(init_file_path, author):
    """处理Excel文件"""
    try:
        df = pd.read_excel(init_file_path)
        print(f"获取{df.shape[0]}条笔记（含重复）")
        
        # 数据处理
        df['点赞数'] = df['点赞数'].apply(convert_likes_to_number)
        df = df.drop_duplicates()
        df = df.sort_values(by='点赞数', ascending=False)
        
        # 生成新的文件名，加入时间戳避免重名
        timestamp = time.strftime("%H%M%S")
        final_file_path = f"小红书作者主页所有笔记-{author}-{df.shape[0]}条-{timestamp}.xlsx"
        
        try:
            df.to_excel(final_file_path, index=False)
        except PermissionError:
            print(f"无法写入文件 {final_file_path}，尝试使用备用文件名...")
            # 如果写入失败，尝试在文件名中加入随机数
            random_suffix = random.randint(1, 1000)
            final_file_path = f"小红书作者主页所有笔记-{author}-{df.shape[0]}条-{timestamp}-{random_suffix}.xlsx"
            df.to_excel(final_file_path, index=False)
        
        # 调整列宽
        auto_resize_column(final_file_path)
        print(f"数据已保存到：{final_file_path}")
        return final_file_path
        
    except Exception as e:
        print(f"处理Excel文件时出错: {str(e)}")
        return None

def auto_resize_column(excel_path):
    """自动调整Excel列宽"""
    wb = openpyxl.load_workbook(excel_path)
    ws = wb.active
    for col in ws.iter_cols(min_col=1, max_col=5):
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[column].width = max_length + 5
    wb.save(excel_path)

def delete_init_file(file_path):
    """删除初始文件"""
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"已删除初始化excel文件：{file_path}")

def main(author_url=None, note_num=None):
    try:
        # 创建安全的输出函数
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
        
        # 第一次运行需要登录
        safe_print("正在初始化...")
        sign_in()
        
        # 如果没有传入参数，使用默认值
        if author_url is None:
            author_url = "https://www.xiaohongshu.com/user/profile/5c56f621000000001a01f759"
        if note_num is None:
            note_num = 62
            
        times = math.ceil(note_num / 20 * 1.1)
        safe_print(f"需要执行翻页次数为：{times}")
        
        # 初始化保存文件
        formatted_time = time.strftime("%Y-%m-%d %H%M%S")
        init_file_path = f'小红书作者主页所有笔记-{formatted_time}.xlsx'
        recorder = Recorder(path=init_file_path, cache_size=100)
        
        try:
            # 执行爬取
            author = open_author_page(author_url)
            safe_print(f"开始获取作者 {author} 的笔记...")
            crawler(times, recorder)
            recorder.record()
            
            # 处理数据并保存
            final_file_path = process_excel(init_file_path, author)
            if final_file_path:
                delete_init_file(init_file_path)
                safe_print(f"数据已保存到：{final_file_path}")
                
        except Exception as e:
            safe_print(f"爬取过程出错: {str(e)}")
            logging.error(f"爬取过程出错: {str(e)}", exc_info=True)
            
    except Exception as e:
        error_msg = f"程序执行出错: {str(e)}"
        logging.error(error_msg, exc_info=True)
        try:
            if hasattr(sys.stdout, 'write'):
                sys.stdout.write(f"{error_msg}\n")
        except:
            pass
    finally:
        # 确保关闭浏览器
        try:
            if 'page' in globals():
                page.quit()
        except:
            pass

if __name__ == '__main__':
    main()
