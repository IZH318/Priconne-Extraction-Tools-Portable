import io
import UnityPy

# all of the following would work
src = "file_path"
src = b"bytes"
src = io.BytesIO(b"Streamable")

env = UnityPy.load(src)

for obj in env.objects:
    ...

# saving an edited file
    # apply modifications to the objects
    # don't forget to use data.save()
    ...
with open(dst, "wb") as f:
    f.write(env.file.save())
