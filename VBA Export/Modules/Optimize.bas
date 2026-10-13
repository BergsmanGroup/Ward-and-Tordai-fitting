Attribute VB_Name = "Optimize"
'This module varies the parameters slected by the user in attempts to minimze the error between
'the calculated solution and the experimental data.  The code uses a Nelder-Mead Optimization scheme
'("Convergence properties of the Nelder-Mead Simplex Method in Low Dimensions"
'Society for industrial applied Mathematics 1998, Lagarias, J.)
'
'The subroutine requires that the Ward and Tordai solution is running flawlessly

Function ParameterOptimization()

Dim Nvar As Integer

' determine how many variables are changing
Nvar = 0#
For i = 0 To 6
    If Sheet3.Cells(48 + i, 2) = True Then Nvar = Nvar + 1
Next i
Sheet3.Cells(56, 2) = Nvar
Sheet3.Cells(66, 1).Clear
If Nvar > 0 Then
    loadExpData
    BaseSimplex
    For i = 1 To 60
        newSimplex
        Sheet3.Cells(65, 1) = i
    Next i
End If

End Function

Sub loadExpData()
' determines the number of data points

NData = 0#
For i = 0 To 1000
    If (Not Sheet2.Cells(38 + i, 8) = 0) Then NData = NData + 1
Next i

Sheet3.Cells(57, 2) = NData

End Sub


Sub SumError(x As Integer)

Dim pos As Integer, _
    NData As Integer, _
    expTime(500) As Double, _
    expST(500) As Double, _
    ST(500) As Double, _
    f As Double

' Load the experimental data and determine how many data points there are

NData = Sheet3.Cells(57, 2)

For i = 0 To NData - 1
    expTime(i) = Sheet2.Cells(38 + i, 8)
    expST(i) = Sheet2.Cells(38 + i, 9)
Next i

'Determine the total sum of the error squared
pos = 0
f = 0
For i = 0 To NData - 1
    For j = pos To 1000
        If t(j) >= expTime(i) Then
            f = f + (s(j) - expST(i)) ^ 2
            pos = j
            Exit For
        End If
    Next j
Next i

Sheet3.Cells(55, x + 3) = f

End Sub

Sub newSimplex()
' performs the next itteration of the NM algotithm once the base simplex has been created

Dim Nvar As Integer

Nvar = Sheet3.Cells(56, 2)

' here order the simplex
OrderSimplex

' clear old data here
Sheet3.Cells.Range(Sheet3.Cells(48, Nvar + 4), Sheet3.Cells(55, Nvar + 6)).Clear

' determine the centroid of the ordered simplex
For i = 0 To Nvar - 1
    For j = 0 To 6
        Sheet3.Cells(48 + j, 4 + Nvar) = Sheet3.Cells(48 + j, 4 + Nvar) + Sheet3.Cells(48 + j, 3 + i) / Nvar
    Next j
Next i

' calculate the reflection point error
reflect
' If f1 <= fr < fn (is somewhere in the middle) then accept the reflection point and discard fn+1
If Sheet3.Cells(55, 3) <= Sheet3.Cells(55, Nvar + 5) And Sheet3.Cells(55, Nvar + 5) < Sheet3.Cells(55, Nvar + 2) Then
    Update (1)
' If fr < f1 (is the best so far) then calculate the expansion point error xe
ElseIf Sheet3.Cells(55, Nvar + 5) < Sheet3.Cells(55, 3) Then
    expand
    ' If fe < fr (meaning that was a good direction to expand) accept xe and terminate iteration
    If Sheet3.Cells(55, Nvar + 6) < Sheet3.Cells(55, Nvar + 5) Then
        Update (2)
    Else ' accept fr and terminate iteration
        Update (1)
    End If
' If fr > fn (is pretty bad) perform a contraction
ElseIf Sheet3.Cells(55, Nvar + 5) >= Sheet3.Cells(55, Nvar + 2) Then
    ' If fn <= fr < fn+1 (xr is stirctly better than xn+1) perform an outisde contraction
    If Sheet3.Cells(55, Nvar + 2) <= Sheet3.Cells(55, Nvar + 5) And Sheet3.Cells(55, Nvar + 5) < Sheet3.Cells(55, Nvar + 3) Then
        contract (1)
        ' If fc <= fr then accept xc and terminate the iteration
        If Sheet3.Cells(55, Nvar + 6) <= Sheet3.Cells(55, Nvar + 5) Then
            Update (2)
        Else ' perform a shrink step
            shrink
        End If
    'If fr >= fn+1 (the worst evaluated point) then perform an inside contraction
    ElseIf Sheet3.Cells(55, Nvar + 5) >= Sheet3.Cells(55, Nvar + 3) Then
        contract (2)
        ' If fc <= fn+1 then accept xc and terminate the iteration
        If Sheet3.Cells(55, Nvar + 6) <= Sheet3.Cells(55, Nvar + 3) Then
            Update (2)
        Else ' perform a shrink step
            shrink
        End If
    End If
End If

End Sub

Sub noNeg(x)
' disallows negative and unrealistic values for parameters during NM optimization
' also fits the isotherm parameters to match the long time data assuming langmuir isotherm

Dim R As Double, _
    sf As Double, _
    NData As Integer, _
    pi_nRT As Double

R = 83145000
NData = Sheet3.Cells(57, 2)
sf = Sheet2.Cells(38 + NData - 1, 9)
pi_nRT = (so - sf) / (RT)

If aL <= 0 Then aL = 1E-17
Sheet3.Cells(48, x + 3) = aL

If Ginf <= 0 Then Ginf = 1E-17
If Ginf >= 0.000001 Then Ginf = 0.000001
Sheet3.Cells(49, x + 3) = Ginf

If kL >= 0 Then kL = -0.01
Sheet3.Cells(50, x + 3) = kL

If pL <= 0 Then pL = 0.01
Sheet3.Cells(51, x + 3) = pL

If D <= 0 Then D = 0.000000001
Sheet3.Cells(52, x + 3) = D

If C(0) <= 0 Then C(0) = 1E-17
Sheet3.Cells(53, x + 3) = C(0)

If RT <= 0 Then RT = R * 273.15
Sheet3.Cells(54, x + 3) = (RT / R) - 273.15

' for the langmuir isotherm calculate the Ginf term for a given aL and long time Surface tension data
' other isotherms (with 3+ parameters require much more work than this and it might be easier to just use pure NM)
If Sheet3.Cells(59, 2) = True And Sheet3.Cells(17, 2) = 1 Then
    Ginf = -pi_nRT / Log(1 - C(0) / (aL + C(0)))
    Sheet3.Cells(49, x + 3) = Ginf
    Sheet3.Cells(60, 2) = 1
End If
    
End Sub

Sub reflect()  ' perform a reflection away from the worst point
Dim rho As Integer, _
    Nvar As Integer

rho = 1
Nvar = Sheet3.Cells(56, 2)

For i = 0 To 6
    Sheet3.Cells(48 + i, Nvar + 5) = Sheet3.Cells(48 + i, Nvar + 4) * (1 + rho) - rho * Sheet3.Cells(48 + i, Nvar + 3)
Next i

UpdateAndRun (Nvar + 2)

End Sub

Sub expand()    ' expand because the reflection was sucessful

Dim rho As Integer, _
    chi As Integer, _
    Nvar As Integer
    
rho = 1
chi = 2
Nvar = Sheet3.Cells(56, 2)

For i = 0 To 6
    Sheet3.Cells(48 + i, Nvar + 6) = Sheet3.Cells(48 + i, Nvar + 4) * (1 + rho * chi) - rho * chi * Sheet3.Cells(48 + i, Nvar + 3)
Next i

UpdateAndRun (Nvar + 3)

End Sub

Sub contract(InOut As Integer) '1 for outside, else for inside
' search between reflected point and xn+1

Dim rho As Integer, _
    chi As Single, _
    Nvar As Integer
    
rho = 1
gamma = 0.5
Nvar = Sheet3.Cells(56, 2)

If InOut = 1 Then
    For i = 0 To 6
        Sheet3.Cells(48 + i, Nvar + 6) = Sheet3.Cells(48 + i, Nvar + 4) * (1 + rho * gamma) - rho * gamma * Sheet3.Cells(48 + i, Nvar + 3)
    Next i
Else
    For i = 0 To 6
        Sheet3.Cells(48 + i, Nvar + 6) = Sheet3.Cells(48 + i, Nvar + 4) * (1 - gamma) + gamma * Sheet3.Cells(48 + i, Nvar + 3)
    Next i
End If
    
UpdateAndRun (Nvar + 3)

End Sub

Sub shrink()
' decrease the size of the entire simplex because it's zeroed in on some good parameters

Dim sigma As Single, _
    Nvar As Integer
    
Nvar = Sheet3.Cells(56, 2)
sigma = 0.5

For i = 1 To Nvar
    For j = 0 To 6
    Sheet3.Cells(48 + j, 3 + i) = Sheet3.Cells(48 + j, 3) + sigma * (Sheet3.Cells(48 + j, 3 + i) - Sheet3.Cells(48 + j, 3))
    Next j
    UpdateAndRun (i)
Next i

End Sub

Sub UpdateOptimize(x As Integer)
' reset the parameters before solving the ward and tordai equation

Dim R As Double

R = 83145000

aL = Sheet3.Cells(48, 3 + x)                          'Iso A
Ginf = Sheet3.Cells(49, 3 + x)                        'Iso B
kL = Sheet3.Cells(50, 3 + x)                          'Iso C
pL = Sheet3.Cells(51, 3 + x)                          'Iso D
D = Sheet3.Cells(52, 3 + x)                           'Diff
C(0) = Sheet3.Cells(53, 3 + x)                        'Cb
RT = R * (273.15 + Sheet3.Cells(54, 3 + x))           'Temp

End Sub

Sub OrderSimplex()

Dim e2(6) As Double, _
    Nvar As Integer
    
' order the simplex with the lowest index being the best (least sum of error squared)
Nvar = Sheet3.Cells(56, 2)
For i = 0 To Nvar
    e2(i) = Sheet3.Cells(55, 3 + i)
Next i

For i = 0 To Nvar
    For j = i + 1 To Nvar
        If e2(i) > e2(j) Then
            For k = 0 To 7
                Sheet3.Cells(48 + k, i + 3) = Sheet3.Cells(48 + k, i + 3) + Sheet3.Cells(48 + k, j + 3)
                Sheet3.Cells(48 + k, j + 3) = Sheet3.Cells(48 + k, i + 3) - Sheet3.Cells(48 + k, j + 3)
                Sheet3.Cells(48 + k, i + 3) = Sheet3.Cells(48 + k, i + 3) - Sheet3.Cells(48 + k, j + 3)
            Next k
        End If
    Next j
Next i

End Sub

Sub BaseSimplex()
Dim boolDiff As Boolean, _
    boolIsoParam As Boolean, _
    boolA As Boolean, _
    boolB As Boolean, _
    boolC As Boolean, _
    boolD As Boolean, _
    boolTemp As Boolean, _
    boolConc As Boolean, _
    Nvar As Integer, _
    relError As Double, _
    R As Double


' here generate a base case with random fixed values
' pick a low and high value for every value and then vary depending on the number of elements chosen
' Nvar = sum of bools that are true


' determine how many variables are changing
Nvar = Sheet3.Cells(56, 2)
R = 83145000

' clear old data in the range
Sheet3.Cells.Range(Sheet3.Cells(48, 3), Sheet3.Cells(55, 13)).Clear
Sheet3.Cells.Range(Sheet3.Cells(60, 6), Sheet3.Cells(65, 6)).Clear
    
' create the base simplex
boolA = Sheet3.Cells(48, 2)
boolB = Sheet3.Cells(49, 2)
boolC = Sheet3.Cells(50, 2)
boolD = Sheet3.Cells(51, 2)
boolDiff = Sheet3.Cells(52, 2)
boolConc = Sheet3.Cells(53, 2)
boolTemp = Sheet3.Cells(54, 2)

Sheet3.Cells.Range(Sheet3.Cells(48, 3), Sheet3.Cells(55, 10)).Clear   'clear old data
   
Sheet3.Cells(48, 3) = aL
Sheet3.Cells(49, 3) = Ginf
Sheet3.Cells(50, 3) = kL
Sheet3.Cells(51, 3) = pL
Sheet3.Cells(52, 3) = D
Sheet3.Cells(53, 3) = C(0)
Sheet3.Cells(54, 3) = Sheet3.Cells(9, 2).Value
SumError (0)
    
For i = 0 To Nvar - 1
    Sheet3.Cells(48, i + 4) = -Sheet3.Cells(27, 2).Value * (Int(Not (boolA)) + Int(boolA) * (Rnd * 2))      'IsoA
    aL = Sheet3.Cells(48, i + 4)
    Sheet3.Cells(49, i + 4) = -Sheet3.Cells(28, 2) * (Int(Not (boolB)) + Int(boolB) * (Rnd * 2))            'IsoB
    Ginf = Sheet3.Cells(49, i + 4)
    Sheet3.Cells(50, i + 4) = -Sheet3.Cells(29, 2) * (Int(Not (boolC)) + Int(boolC) * (0.5 + Rnd * 1))      'IsoC
    kL = Sheet3.Cells(50, i + 4)
    Sheet3.Cells(51, i + 4) = -Sheet3.Cells(30, 2) * (Int(Not (boolD)) + Int(boolD) * (0.5 + Rnd * 1))      'IsoD
    pL = Sheet3.Cells(51, i + 4)
    Sheet3.Cells(52, i + 4) = -Sheet3.Cells(7, 2) * (Int(Not (boolDiff)) + Int(boolDiff) * (Rnd * 2))       'Diffusivity
    D = Sheet3.Cells(52, i + 4)
    Sheet3.Cells(53, i + 4) = -Sheet3.Cells(6, 2) * (Int(Not (boolConc)) + Int(boolConc) * (0.5 + Rnd * 1))  'Concentration
    C(0) = Sheet3.Cells(53, i + 4)
    Sheet3.Cells(54, i + 4) = -Sheet3.Cells(9, 2) * (Int(Not (boolTemp)) + Int(boolTemp) * (0.8 + Rnd * 0.4)) 'Temperature
    RT = R * (273.15 + Sheet3.Cells(54, i + 4))
    noNeg (i + 1)
    NumericSolution
    SumError (i + 1)
Next i

End Sub

Sub Update(x As Integer)
' clears xn+1 and accepts the xr(1) or xe(2)/xc(2)

' x = 1 for reflection point
' x = 2 for all expansions and contractions

Dim Nvar As Integer

Nvar = Sheet3.Cells(56, 2)

For i = 0 To 7
    Sheet3.Cells(48 + i, Nvar + 3) = Sheet3.Cells(48 + i, Nvar + 4 + x)
Next i

End Sub

Sub UpdateAndRun(x As Integer)

UpdateOptimize (x)   ' update parameters for next numeric sln
noNeg (x)            ' make sure parameters are physical
NumericSolution      ' solve ward and tordai equation
SumError (x)         ' compute sum of error squared

End Sub
