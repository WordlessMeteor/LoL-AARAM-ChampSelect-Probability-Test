from typing import Iterable

class Patch:
    def __init__(self, *parts: Iterable[int | str]): #初始化版本对象（Initializes the patch object）
        '''
        版本类的构造函数。<br>The constructor of `Patch` class.
        
        :param *parts: 一个由正整数组成的可迭代对象，或者是一个仅由整数和英文句点组成的版本号字符串。<br>An iterable object composed of only positive integers or a version string composed of only digital characters and English dots.
        :type *parts: Iterable[int] | str
        '''
        self.parts: list[int] = []
        if len(parts) == 1 and isinstance(parts[0], str):
            if parts[0] == "latest":
                self.parts = [99, 97] #正式服版本总是视为99.97版本（Latest version is always considered as Patch 99.97）
            elif parts[0] == "pbe":
                self.parts = [99, 98] #测试服版本总是视为99.98版本（PBE version is always considered as Patch 99.98）
            else:
                numbers: list[str] = parts[0].split(".")
                try:
                    self.parts = list(map(int, numbers))
                except ValueError:
                    raise ValueError("All parts must be non-negative integers.")
        else:
            for part in parts:
                if isinstance(part, int) and part >= 0:
                    self.parts.append(part)
                else:
                    raise ValueError("All parts must be non-negative integers.")
        
    def __str__(self) -> str: #生成版本字符串（Generate the patch string）
        if self.parts == [99, 97]:
            return "latest"
        elif self.parts == [99, 98]:
            return "pbe"
        else:
            return ".".join(str(part) for part in self.parts)

    def __repr__(self) -> str: #自我描述（Self description）
        return f'Patch({", ".join(str(part) for part in self.parts)})'

    def __eq__(self, other) -> bool: #重载等号（Overloads the equal sign）
        if not isinstance(other, Patch):
            return False
        return self.parts == other.parts

    def __lt__(self, other) -> bool: #重载小于号（Overloads the less-than sign）
        if not isinstance(other, Patch):
            return NotImplemented
        
        for i in range(max(len(self.parts), len(other.parts))):
            self_part = self.parts[i] if i < len(self.parts) else 0
            other_part = other.parts[i] if i < len(other.parts) else 0
            if self_part < other_part:
                return True
            elif self_part > other_part:
                return False
        
        return False

    def __gt__(self, other) -> bool: #重载大于号（Overloads the greater-than sign）
        if not isinstance(other, Patch):
            return NotImplemented
        return not (self < other or self == other)

    def __le__(self, other) -> bool: #重载小于等于号（Overloads the less-than-or-equal-to sign）
        if not isinstance(other, Patch):
            return NotImplemented
        return self < other or self == other

    def __ge__(self, other) -> bool: #重载大于等于号（Overloads the greater-than-or-equal-to sign）
        if not isinstance(other, Patch):
            return NotImplemented
        return self > other or self == other

    def __ne__(self, other) -> bool: #重载不等号（Overloads the not-equal-to sign）
        if not isinstance(other, Patch):
            return NotImplemented
        return not self == other
    
    @classmethod
    def sort(cls, patchList: list[Patch]) -> list[Patch]: #利用插入排序算法对版本列表进行升序排列（Sorts a patch list through the insertion sort algorithm）
        '''
        对版本列表进行升序排列。<br>Sort a list of `Patch` objects in ascending order.
        
        :param patchList: 由版本对象组成的列表。<br>A list of `Patch` objects.
        :type patchList: list[Patch]
        :return: 排序后的版本对象列表。<br>An ordered list of `Patch` objects.
        :rtype: list[Patch]
        '''
        if isinstance(patchList, list) and all(map(lambda x: isinstance(x, Patch), patchList)):
            for i in range(1, len(patchList)):
                tmp = patchList[i] #将第i个元素临时存储（Temporarily stores the i-th element of `patchList`）
                j = i - 1
                while j >= 0 and tmp < patchList[j]: #如果检测到第i个元素比第(j = i - 1)个元素小，就要逐渐减小j，直到找到一个j，使得第j个元素小于第i个元素，此时第j + 1个元素仍然大于第i个元素。把j + 1及以后的元素右移，空出的位置再插入第i个元素（1f an i-th element is detected to be less than the j-th element, namely the (i - 1)th element, then the program decrements j until it finds a j such that the j-th element is less than the i-th element, while the (j + 1)-th element is still greater than the i-the element. Then, shift all elements between the current j-th and i-th elements and insert the i-th elements into the empty space）
                    patchList[j + 1] = patchList[j]
                    j -= 1
                patchList[j + 1] = tmp
            return patchList
        else:
            raise TypeError("The parameter patchList must be a list of Patch objects.")

def FindPostPatch(patch: Patch, patchList: list[Patch]) -> str: #二分查找某个版本号在DataDragon数据库的后一个版本（Binary search for the precedent patch of a given patch in the patch list archived in DataDragon database）
    '''
    从一个版本对象列表中找到某个版本的后继版本。<br>Find a patch's successive patch among a list.
    
    :param patch: 要寻找的版本对象。可不存在于版本列表中。<br>A `Patch` object to query. It doesn't have to be in `patchList`.
    :type patch: Patch
    :param patchList: 参考版本对象列表。<br>A reference list of `Patch` object.
    :type patchList: list[Patch]
    :return: 待寻找的版本对象的后继版本字符串。<br>A string of the successive patch of the queried `Patch` object.
    :rtype: str
    '''
    leftIndex: int = 0
    rightIndex: int = len(patchList) - 1
    mid: int = (leftIndex + rightIndex) // 2
    count: int = 0 #函数调试阶段的保护机制（A protecion mechanism during rebugging this function）
    #print("[" + str(count) + "]", leftIndex, mid, rightIndex)
    while leftIndex < rightIndex:
        count += 1
        if patch < patchList[mid]:
            leftIndex = mid + 1
            mid = (leftIndex + rightIndex) // 2
        elif patchList[mid] < patch:
            rightIndex = mid
            mid = (leftIndex + rightIndex) // 2
        else:
            return str(patchList[mid - 1])
        #print("[" + str(count) + "]", leftIndex, mid, rightIndex)
        if count >= 15:
            print("程序即将进入死循环！请检查算法！\nThe program is stepping into a dead loop! Please check the algorithm!")
            return "NaN"
    if mid >= 1:
        return str(patchList[mid - 1])
    else:
        print("该版本为美测服最新版本，暂未收录在DataDragon数据库中。\nThis version is the latest version on PBE and isn't archived in DataDragon database for now.")
        return "pbe"
