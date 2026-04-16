# RunTime Tracker

> 本项目由 AI 辅助开发
> 版本: 1.0.0

RunTime Tracker 是一个设备使用情况监控工具，可以实时跟踪设备上运行的应用程序，并将数据上报到服务器进行分析。

## 功能特性

- 实时监控前台应用程序
- 自动上报设备使用数据到服务器
- 显示电池状态和充电情况
- 支持主题切换（浅色、深色、跟随系统）
- 可配置的监控间隔和上报设置
- 详细的日志记录和查看功能

## 系统要求

- Windows 操作系统
- Python 3.7 或更高版本

## 安装指南

### 方法一：直接运行（开发模式）

1. 克隆或下载项目到本地
2. 安装依赖项：
   ```bash
   pip install -r requirements.txt
   ```
3. 运行应用：
   ```bash
   python main.py
   ```

### 方法二：使用打包版本（推荐）

1. 下载打包好的可执行文件
2. 解压到任意目录
3. 双击 `RunTimeTracker.exe` 运行

## 配置说明

首次运行应用时，会使用默认配置。您可以在"配置"页面修改以下设置：

- **API设置**：
  - API地址：数据上报的服务器地址
  - 密钥：用于验证上报请求
  - 设备ID：标识当前设备的唯一名称

- **监控设置**：
  - 监控间隔：检查前台应用的时间间隔（秒）
  - 上报功能：是否启用数据上报

- **主题设置**：
  - 跟随系统：使用系统当前主题
  - 浅色主题：使用浅色界面
  - 深色主题：使用深色界面

## 使用指南

1. **主页面**：显示当前应用、电池状态和设备信息
2. **日志页面**：查看和导出应用日志
3. **配置页面**：修改应用设置
4. **关于页面**：查看项目信息和相关链接

## 开机自启动配置说明
### 方法：创建 VBS 脚本实现开机自启（管理员权限）
1. 创建 VBS 脚本文件
   
   在应用目录下新建一个文本文件，命名为 start.vbs ，内容如下：
   
   ```
   Set objShell = CreateObject
   ("Shell.Application")
   
   ' 程序路径和工作目录
   strProgramPath = 
   "G:\Users\Administrator\Desktop\Ru
   nTimeTracker\RunTimeTracker.exe"
   strWorkingDir = 
   "G:\Users\Administrator\Desktop\Ru
   nTimeTracker"
   
   ' 以管理员身份运行 (runas)，窗口正常显
   示 (1)
   objShell.ShellExecute 
   strProgramPath, "", 
   strWorkingDir, "runas", 1
   ``` 注意 ：请将路径修改为您实际的安装目录
2. 添加到开机自启动
   
   - 按 Win + R 打开运行窗口
   - 输入 shell:startup 回车，打开启动文件夹
   - 将创建的 start.vbs 文件复制到启动文件夹中
3. 验证
   
   重启电脑后，应用将自动以管理员身份启动
### 说明
- runas 参数表示以管理员权限运行程序
- 1 参数表示窗口正常显示
- 如果不想每次弹管理员提示框，可以右键 start.vbs → 属性 → 兼容性 → 勾选"以管理员身份运行"
### 卸载自启动
删除启动文件夹 shell:startup 中的 start.vbs 文件即可。

## 数据上报

应用会定期上报以下数据到服务器：

- 当前运行的应用名称
- 应用运行状态
- 电池电量和充电状态
- 设备ID

## 项目链接

- [GitHub - RunTime_Tracker_Client_Windows](https://github.com/CSSQY/RunTime_Tracker_Client_Windows)

## 相关项目

- [GitHub - RunTime_Tracker (服务端)](https://github.com/1812z/RunTime_Tracker)
- [GitHub - Tracker_Client (Android客户端)](https://github.com/1812z/Tracker_Client)
- [GitHub - PyQt-Fluent-Widgets (UI框架)](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)

## 常见问题

### 应用无法启动
- 检查是否安装了所有依赖项
- 查看日志文件了解具体错误信息

### 数据上报失败
- 检查网络连接
- 验证API地址和密钥是否正确
- 查看日志文件了解具体错误信息

### 监控不工作
- 检查监控间隔设置是否合理
- 确保上报功能已启用
- 查看日志文件了解具体错误信息

## 日志文件

日志文件存储在 `logs` 目录中，命名格式为 `runtime_tracker_YYYY-MM-DD.log`。您可以在"日志"页面查看和导出日志。

## 开源许可

本项目采用 MIT 许可证。

## 开发者

- **作者**: CSSQY

## 联系我们

- GitHub Issues: [https://github.com/CSSQY/RunTime_Tracker_Client_Windows/issues](https://github.com/CSSQY/RunTime_Tracker_Client_Windows/issues)
