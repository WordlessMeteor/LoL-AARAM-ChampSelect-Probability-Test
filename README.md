本存储库通过自动实现<ins>开启游戏</ins>、<ins>选择英雄</ins>和<ins>退出英雄选择</ins>，来提高在全随机模式中期望选择固定英雄时的行动效率。

本存储库只做**临时**用途。待[主要脚本仓库](https://github.com/WordlessMeteor/LoL-DIY-Programs)完成所有提交后，本存储库将被**删除**。

脚本环境配置步骤：
1. 访问[Python官网](www.python.org)。
2. 下载和安装最新版本的Python。
3. 通过`pip install [包名]`命令安装所需的Python库。
    - lcu_driver
        - 本人复刻了[lcu_driver库](https://github.com/WordlessMeteor/lcu-driver/tree/master/lcu_driver)文件，以便相应的拉取请求在经过lcu_driver库的作者同意合并之前，或者被作者拒绝时，用户仍然可以下载体验本存储库的lcu_driver库文件。
        - 本人只负责**根据本程序集需要**对该存储库中的库文件进行修改，没有义务将其它GitHub用户对库文件的修改与本人对库文件的修改进行合并。不过，欢迎任何用户**基于本程序集的更新**对库文件更新提出意见和建议👏
        - 如果需要使用本人修改的lcu_driver库，请按照如下步骤进行。
            1. 打开[本人的lcu-driver存储库主页](https://github.com/WordlessMeteor/lcu-driver)。
            2. 单击<ins>绿色Code按钮</ins>，再单击<ins>DownloadZIP</ins>，下载本存储库的源代码。
            3. 将下载好的压缩包【解压到当前文件夹】。
                - 不用担心解压完成之后会不会有一大堆文件分散在文件夹里面。从GitHub上下载的源代码应该已经放在了一个文件夹里面。
            4. 打开Python存储库的目录。
                - 一般位于`C:\Users\[用户名]\AppData\Local\Programs\Python\Python[版本号]\Lib\site-packages`。
                    - 如我的用户名是`19250`，使用的Python版本是<ins>3.14.2</ins>，则应打开\
                    `C:\Users\19250\AppData\Local\Programs\Python\Python314\Lib\site-packages`。
                - 如果上一条方法行不通，请先在命令行中输入`pip install lcu_driver`以安装`lcu_driver`库，再使用[Everything软件](https://www.voidtools.com/zh-cn/)搜索<ins>lcu_driver</ins>关键字，从而定位到Python存储库的位置。
            5. 在解压好的文件中找到`lcu_driver`文件夹，将其复制到上面的目录中。如果提示文件已存在，请选择覆盖。
            6. 若要恢复原始lcu_driver库文件，请先在命令行中输入`pip uninstall lcu_driver`，再输入`pip install lcu_driver`重新安装。
    - openpyxl
    - pandas
    - requests
    - pyperclip
    - pickle
    - urllib
    - wcwidth
    - bs4
    - keyboard

    如果没有科学上网的环境且安装过慢，可以尝试在pip后指定镜像源。如`pip install [包名] -i https://pypi.tuna.tsinghua.edu.cn/simple`，从清华源安装Python库。
4. 打开终端。
5. 使用`cd [文件夹路径]`将工作目录切换到当前工作目录。
6. 输入`python [脚本路径]`执行脚本。
    - 如果出现ImportError，一般情况下再次执行pip安装命令完善缺失的Python库即可。
