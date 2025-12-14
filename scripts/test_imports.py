import traceback
modules = ['env','data','server','dglab_api','utils']
for m in modules:
    try:
        __import__(m)
        print(m+': OK')
    except Exception:
        print('--- ERROR importing',m)
        traceback.print_exc()