VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmError 
   Caption         =   "Program Runtime Errors"
   ClientHeight    =   4620
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   4680
   OleObjectBlob   =   "frmError.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "frmError"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Private Sub cmdErrorClose_Click()

'Hides the ErrorForm
frmError.lstError.Clear
frmError.Hide

End Sub
