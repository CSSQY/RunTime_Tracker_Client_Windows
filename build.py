import os
import shutil
import subprocess

# 清理之前的构建目录
def clean_build():
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('RunTimeTracker.spec'):
        os.remove('RunTimeTracker.spec')
    print("清理完成")

# 执行打包命令
def build_executable():
    # 构建命令
    cmd = [
        'pyinstaller',
        '--name', 'RunTimeTracker',
        '--windowed',
        '--icon', '图标.ico',
        '--add-data', 'apps.json;.',
        '--add-data', 'config.json;.',
        '--add-data', '图标.png;.',
        '--add-data', '图标.ico;.',
        'main.py'
    ]
    
    print("开始打包...")
    try:
        subprocess.run(cmd, check=True)
        print("打包完成")
        
        # 复制必要的文件到dist目录
        if os.path.exists('dist'):
            # 复制apps.json
            if os.path.exists('apps.json'):
                shutil.copy('apps.json', 'dist/')
                print("已复制 apps.json")
            
            # 复制config.json（如果存在）
            if os.path.exists('config.json'):
                shutil.copy('config.json', 'dist/')
                print("已复制 config.json")
            
            # 创建logs目录
            logs_dir = os.path.join('dist', 'logs')
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
                print("已创建 logs 目录")
                
            # 复制README.md
            if os.path.exists('README.md'):
                shutil.copy('README.md', 'dist/')
                print("已复制 README.md")
            
            # 复制图标文件到项目根目录（供打包时使用
            if os.path.exists('图标.png'):
                print("图标.png 已在项目目录中")
            
            # 复制图标.ico
            if os.path.exists('图标.ico'):
                shutil.copy('图标.ico', 'dist/')
                print("已复制 图标.ico")
                
    except subprocess.CalledProcessError as e:
        print(f"打包失败: {e}")

if __name__ == "__main__":
    # 跳过清理步骤，直接执行打包命令
    build_executable()
