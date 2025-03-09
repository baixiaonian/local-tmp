import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import queue
import os
from datetime import datetime
from extract_search import sign_in as search_sign_in, main as search_main, get_executable_path
from extract_author import sign_in as author_sign_in, main as author_main
import logging

class RedirectText:
    """重定向输出到GUI文本框"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.queue = queue.Queue()
        self.updating = True
        self._thread = threading.Thread(target=self.update_text_widget, daemon=True)
        self._thread.start()

    def write(self, string):
        if string:  # 只处理非空字符串
            self.queue.put(string)

    def flush(self):
        pass

    def update_text_widget(self):
        while self.updating:
            try:
                text = self.queue.get(timeout=0.1)  # 使用超时等待
                if text:
                    self.text_widget.insert('end', text)
                    self.text_widget.see('end')
                    self.text_widget.update()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"更新文本出错: {str(e)}")

    def stop(self):
        self.updating = False

class XHSDataAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title("小红书数据助手")
        self.root.geometry("800x600")
        
        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 创建选项卡
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 创建搜索和作者主页选项卡
        self.search_frame = ttk.Frame(self.notebook, padding="10")
        self.author_frame = ttk.Frame(self.notebook, padding="10")
        
        self.notebook.add(self.search_frame, text="搜索采集")
        self.notebook.add(self.author_frame, text="作者数据")
        
        # 初始化各个选项卡的内容
        self.init_search_tab()
        self.init_author_tab()
        
        # 创建日志显示区域
        self.create_log_area()
        
        # 创建并设置日志重定向
        self.redirect = RedirectText(self.log_text)
        
        # 确保程序关闭时恢复标准输出
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def init_search_tab(self):
        """初始化搜索选项卡"""
        # 关键词输入
        ttk.Label(self.search_frame, text="关键词:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.keyword_entry = ttk.Entry(self.search_frame, width=40)
        self.keyword_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        # 页数输入
        ttk.Label(self.search_frame, text="页数:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.pages_entry = ttk.Entry(self.search_frame, width=10)
        self.pages_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.pages_entry.insert(0, "1")
        
        # 搜索按钮
        self.search_button = ttk.Button(self.search_frame, text="开始采集", command=self.start_search)
        self.search_button.grid(row=2, column=0, columnspan=2, pady=10)

    def init_author_tab(self):
        """初始化作者主页选项卡"""
        # 作者主页链接输入
        ttk.Label(self.author_frame, text="作者主页链接:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.author_url_entry = ttk.Entry(self.author_frame, width=80)
        self.author_url_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        # 笔记数量输入
        ttk.Label(self.author_frame, text="笔记数量:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.note_count_entry = ttk.Entry(self.author_frame, width=10)
        self.note_count_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.note_count_entry.insert(0, "10")
        
        # 采集按钮
        self.author_button = ttk.Button(self.author_frame, text="开始获取", command=self.start_author)
        self.author_button.grid(row=2, column=0, columnspan=2, pady=10)

    def create_log_area(self):
        """创建日志显示区域"""
        # 日志显示
        self.log_frame = ttk.LabelFrame(self.main_frame, text="运行日志", padding="5")
        self.log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=20)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 清除按钮
        self.clear_button = ttk.Button(self.log_frame, text="清除日志", command=self.clear_log)
        self.clear_button.grid(row=1, column=0, pady=5)

    def clear_log(self):
        """清除日志"""
        self.log_text.delete(1.0, tk.END)

    def on_closing(self):
        """程序关闭时的清理工作"""
        try:
            if hasattr(self, 'redirect'):
                self.redirect.stop()
            self.root.destroy()
        except Exception as e:
            logging.error(f"程序关闭时出错: {str(e)}")
            self.root.destroy()

    def start_search(self):
        """启动搜索爬虫"""
        keyword = self.keyword_entry.get().strip()
        pages = self.pages_entry.get().strip()
        
        if not keyword:
            messagebox.showerror("错误", "请输入关键词")
            return
            
        try:
            pages = int(pages)
            if pages < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "页数必须是正整数")
            return
            
        self.search_button.state(['disabled'])
        threading.Thread(target=self.run_search_crawler, args=(keyword, pages), daemon=True).start()

    def start_author(self):
        """启动作者主页爬虫"""
        url = self.author_url_entry.get().strip()
        note_count = self.note_count_entry.get().strip()
        
        if not url:
            messagebox.showerror("错误", "请输入作者主页链接")
            return
            
        try:
            note_count = int(note_count)
            if note_count < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "笔记数量必须是正整数")
            return
            
        self.author_button.state(['disabled'])
        threading.Thread(target=self.run_author_crawler, args=(url, note_count), daemon=True).start()

    def run_search_crawler(self, keyword, pages):
        """运行搜索爬虫"""
        old_stdout = sys.stdout  # 在 try 外保存原始输出
        try:
            sys.stdout = self.redirect
            try:
                print(f"开始搜索采集 - 关键词: {keyword}, 页数: {pages}")
                search_main(keyword=keyword, pages=pages)
                print("搜索采集完成")
            except Exception as e:
                print(f"采集出错: {str(e)}")
                logging.error(f"搜索采集出错: {str(e)}", exc_info=True)
        except Exception as e:
            logging.error(f"输出重定向出错: {str(e)}", exc_info=True)
        finally:
            sys.stdout = old_stdout  # 恢复原始输出
            self.search_button.state(['!disabled'])

    def run_author_crawler(self, url, note_count):
        """运行作者主页爬虫"""
        old_stdout = sys.stdout  # 在 try 外保存原始输出
        try:
            sys.stdout = self.redirect
            try:
                print(f"开始获取作者数据 - URL: {url}, 笔记数: {note_count}")
                author_main(author_url=url, note_num=note_count)
                print("作者数据获取完成")
            except Exception as e:
                print(f"获取出错: {str(e)}")
                logging.error(f"作者数据获取出错: {str(e)}", exc_info=True)
        except Exception as e:
            logging.error(f"输出重定向出错: {str(e)}", exc_info=True)
        finally:
            sys.stdout = old_stdout  # 恢复原始输出
            self.author_button.state(['!disabled'])

def setup_logging():
    """设置日志"""
    log_path = os.path.join(get_executable_path(), 'runtime.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def main():
    try:
        setup_logging()
        logging.info("程序启动")
        root = tk.Tk()
        app = XHSDataAssistant(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"程序运行出错: {str(e)}", exc_info=True)
        messagebox.showerror("错误", f"程序运行出错: {str(e)}\n请查看runtime.log获取详细信息")

if __name__ == "__main__":
    main() 