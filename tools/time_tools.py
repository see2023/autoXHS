import datetime
import cnlunar
from config.config_manager import config

# num为数字，返回num的中文大写表示
def num_to_cn(num):
    num = int(num)
    if num == 0:
        return '零'
    elif num < 0:
        return '负' + num_to_cn(abs(num))
    elif num < 10:
        return ['', '一', '二', '三', '四', '五', '六', '七', '八', '九'][num]
    elif num < 100:
        return num_to_cn(num // 10) + '十' + num_to_cn(num % 10)
    elif num < 1000:
        return num_to_cn(num // 100) + '百' + num_to_cn(num % 100)
    elif num < 10000:
        return num_to_cn(num // 1000) + '千' + num_to_cn(num % 1000)
    else:
        return num_to_cn(num // 10000) + '万' + num_to_cn(num % 10000)

# 返回当前日期、时间，和农历日期的字符串
def get_lunar():
    now = datetime.datetime.now()
    lunar = cnlunar.Lunar(now, godType='8char')
    month_cn = lunar.lunarMonthCn
    month_cn = month_cn.replace('小', '').replace('大', '')
    return now.strftime('%Y-%m-%d %H:%M:%S') + '，星期' + num_to_cn(now.strftime('%w')) +', 农历' +  month_cn + lunar.lunarDayCn

def get_time_and_location() -> str:
    return f"当前地点是:%s， 时间：%s。 " % (config.llm.get('location'),  get_lunar())



if __name__ == '__main__':
    print(get_lunar())
