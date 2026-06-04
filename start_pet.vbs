' start_pet.vbs — เปิด MyDesktopPet แบบเงียบ (ไม่มีหน้าต่าง console)
' ดับเบิลคลิกเพื่อเปิดเอง หรือใช้สำหรับ auto run ตอนเปิดเครื่อง
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
' โฟลเดอร์ที่ไฟล์ .vbs นี้อยู่ = โฟลเดอร์โปรเจกต์
projDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = projDir
sh.Run "pythonw.exe """ & projDir & "\main.py""", 0, False
