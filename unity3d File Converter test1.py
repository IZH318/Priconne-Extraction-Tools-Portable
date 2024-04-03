import os
import json
from io import BytesIO
from vendor.UnityPack import unitypack
from PIL import ImageOps

def open_asset(export_dir, second_export):
    current_dir = os.getcwd()  # 현재 디렉터리 경로

    for file_name in os.listdir(current_dir):
        if file_name.endswith('.unity3d'):
            import_path = os.path.join(current_dir, file_name)
            with open(import_path, 'rb') as f:
                bundle = unitypack.load(f)
                for asset in bundle.assets:
                    outFiles = []
                    for id, obj in asset.objects.items():
                        data = obj.read()

                        openType = "wb"
                        exportDests = []
                        writeData = ""

                        forceExtract = False

                        # Try to get file names before data so we don't waste computation time extracting things we're not going to overwrite
                        if hasattr(data, "name"):
                            exportDests.append(os.path.join(export_dir, data.name))
                            if second_export:
                                exportDests.append(os.path.join(second_export, data.name))

                        if obj.type == 'Texture2D':
                            for i, dest in enumerate(exportDests):
                                exportDests[i] = dest + ".png"

                        elif obj.type == 'ConstTextScriptableObject':
                            forceExtract = True 

                        if forceExtract or (exportDests and not os.path.exists(exportDests[0])):
                            if obj.type == 'ConstTextScriptableObject':
                                for key, value in data.items():
                                    try:
                                        jsonData = json.dumps(value, indent=4)
                                        outData = {
                                            "writeData": jsonData,
                                            "openType": "w",
                                            "exportDests": [os.path.join(export_dir, key + ".json")]
                                        }
                                        if second_export:
                                            outData["exportDests"].append(os.path.join(second_export, key + ".json"))
                                        outFiles.append(outData)                                
                                    except:
                                        print(key, "not serializable")     

                            elif obj.type == 'TextAsset':
                                writeData = data.script
                                if isinstance(data.script, str):
                                    openType = "w"

                            elif obj.type == 'Texture2D':
                                try:
                                    image = data.image
                                except NotImplementedError as e:
                                    print('\tNotImplementedError: ' + str(e))
                                    continue
                                if image is None:
                                    print('\tEmpty Image')
                                    continue
                                img = ImageOps.flip(image)
                                output = BytesIO()
                                img.save(output, format='png')
                                openType = "wb"
                                writeData = output.getvalue()
                            
                        if writeData:
                            outFiles.append({
                                "writeData": writeData,
                                "exportDests": exportDests,
                                "openType": openType
                            })

                    for outData in outFiles:
                        for dest in outData["exportDests"]:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with open(dest, outData["openType"]) as fi:
                                fi.write(outData["writeData"])
                                print('<DESERIALIZE>', import_path, '->', dest)

if __name__ == "__main__":
    export_dir = os.path.join(os.getcwd(), "export")  # 리소스를 추출할 폴더의 상대 경로
    second_export = os.path.join(os.getcwd(), "second_export")  # 두 번째 폴더의 상대 경로

    open_asset(export_dir, second_export)
