Attribute VB_Name = "WardAndTordai"
'This module represents the current source code set for the Ward and
'Tordai solution subroutines and functions.  It requires some global
'variables to be called in order to work properly.  The required
'globals are as follows:
'[List what globals'are needed].
'
'Other than these values, the subroutine is more or less stand-
'alone.

Sub NumericSolution()

'This section of code carries out the numerical solution to the Ward
'and Tordai equation.  A full solution is accomplished by root binding.

Dim CSum As Double, _
    LSum As Double, _
    GRoot1 As Double, _
    GRoot2 As Double, _
    GRoot3 As Double, _
    GRootSave As Double, _
    CRoot1 As Double, _
    CRoot2 As Double, _
    CRoot3 As Double, _
    EQ As Double, _
    Count As Long, _
    IsoTypeVal As Integer

Sheet2.Cells(26, 2) = "Solving the Ward and Tordai equation..."

'Set initial values.
G(1) = 0
C(1) = 0
s(1) = so
IsoTypeVal = frmMain.lstIsoTypes.ListIndex + 1

'Initialize convolution sums
CSum = 0
LSum = 0

'Begin time vector iterations.
For i = 2 To NTot

   'Make initial guesses at the solution
   If boolRootEst Then
      GRoot1 = GEst(Int(i)) - RootEstTol
      GRoot2 = GEst(Int(i)) + RootEstTol
   Else
      GRoot1 = 0#
      GRoot2 = G(0)
   End If
   If (GRoot1 < 0) Then GRoot1 = 0#
   If (Not IsoTypeVal = 1) And (GRoot2 >= Ginf) Then GRoot2 = 0.9999999999 * Ginf
   
   'Initialize root tweaking parameters if enabled.
   If boolSolTweak Then
      GRootSave = GRoot2 / InitSolTweak
   End If
   
   'Determines the sum of the convolution integral up to time t(i-1).
   CSum = PastBackDiff(Int(i))
   If boolB Then LSum = PastBackCurv(Int(i))
   
   'Set initial tolerance so that it cannot be satisfied.  Initialize
   'break loop counter.
   EQ = 2 * Tol
   Count = 0
   
   'Begin root binding iterations.
   While Abs(EQ) > Tol
   
      'Iterate break infinite loop procedure.  Break loop if stuck.
      Count = Count + 1
      If Count = 10000 Then
            RunErrors = "DST solution cannot satisfy tolerance at iteration " & i _
                & ". Press OK end with current results."
            AdVersion = "Adsorb v1.0"
            MsgBox Title:=AdVersion, Prompt:=RunErrors, Buttons:=vbCritical
            NTot = i - 1
            Exit Sub
      End If
      
      'Root binding!
      GRoot3 = (GRoot1 + GRoot2) / 2
      CRoot1 = AdIso(GRoot1, 2, IsoTypeVal)
      CRoot2 = AdIso(GRoot2, 2, IsoTypeVal)
      CRoot3 = AdIso(GRoot3, 2, IsoTypeVal)
      
      'Check for overflow AdIso, Stop program if present
      If (CRoot1 = 9E+307) Or (CRoot2 = 9E+307) Or (CRoot3 = 9E+307) Then
            RunErrors = "Isotherm calculation overflow at iteration " & i _
                & ". Press OK end with current results."
            AdVersion = "Adsorb v1.0"
            MsgBox Title:=AdVersion, Prompt:=RunErrors, Buttons:=vbCritical
            NTot = i - 1
            Exit Sub
      End If
      
      'Check roots and break if non-convergent.
      EQ1 = Equal(Int(i), GRoot1, CRoot1, CSum, LSum)
      EQ2 = Equal(Int(i), GRoot2, CRoot2, CSum, LSum)
      EQ3 = Equal(Int(i), GRoot3, CRoot3, CSum, LSum)
      If EQ1 * EQ3 < 0 And EQ2 * EQ3 > 0 Then
         GRoot2 = GRoot3
      ElseIf EQ2 * EQ3 < 0 And EQ1 * EQ3 > 0 Then
         GRoot1 = GRoot3
      Else
         'Solution tweaking (scanning) if enabled. Otherwise, break.
         If boolSolTweak Then
            GRoot1 = 0
            GRoot2 = SucSolTweak * GRootSave
            GRootSave = GRoot2
         Else
            RunErrors = "Non-covergence during DST calculation. Press OK end with current results."
            AdVersion = "Adsorb v1.0"
            MsgBox Title:=AdVersion, Prompt:=RunErrors, Buttons:=vbCritical
            NTot = i - 1
            Exit Sub
         End If
      End If
      
      'Final root estimates and equality check.  If loop tolerance is
      'not satisfied, the program will return to start of the While loop.
      G(i) = (GRoot1 + GRoot2) / 2
      C(i) = AdIso(G(i), 2, IsoTypeVal)
      EQ = Equal(Int(i), G(i), C(i), CSum, LSum)
   Wend
   
   'Calculate surface tension and update progress cell.
   s(i) = SurfTen(G(i), IsoTypeVal)
   Sheet2.Cells(27, 2) = i / NTot
   
Next i

End Sub


Function GEst(n As Integer)

'This subroutine provides an estimate of the surface concentration at
'the current time step n.

Dim SlopeA As Double, _
    SlopeB As Double

If n = 2 Then 'No adsorption history, use low time approximation.
    GEst = 1.5 * Sqr(4 * D * t(n) / Pi) * C(0)
Else 'Estimate using adsorption history.
    SlopeA = G(n - 1) - G(n - 2)
    SlopeB = t(n - 1) - t(n - 2)
    GEst = G(n - 1) + (SlopeA / SlopeB) * (t(n) - t(n - 1))
End If

End Function

Function PastBackDiff(n As Integer)

'This function calculates the sum of the Ward and Tordai convolution
'integral up to a time t(i-1).  This function does not take the
'bubble curvature into effect.

Dim PBDA As Double, _
    PBDB As Double, _
    PBDF2A As Double, _
    PBDF2B As Double, _
    PBD As Double, _
    PBDOld As Double

PBD = 0
PBDF2A = 1
PBDF2B = 1

If n = 2 Then
    PastBackDiff = PBD
Else
    For j = 1 To n - 2
        If boolkmic Then 'Calculate micelle correction factors
            PBDF2A = kmicF2(t(n) - t(j + 1))
            PBDF2B = kmicF2(t(n) - t(j))
        End If
        PBDA = 0.5 * (PBDF2A * C(j + 1) + PBDF2B * C(j))
        PBDB = Sqr(t(n) - t(j + 1)) - Sqr(t(n) - t(j))
        If j = 1 Then
            PBD = PBDA * PBDB
            PBDOld = PBD
        Else
            PBD = PBDOld + PBDA * PBDB
            PBDOld = PBD
        End If
    Next j
    PastBackDiff = PBD
End If

End Function
Function PastBackCurv(n As Integer)

'This function calculates the sum of the Ward and Tordai convolution
'integral up to a time t(i-1).  This function calculates adsorption
'due to the bubble curvature.  A better implementation of this would
'be to merge this calculations with the PastBackDiff function.  This
'would probably decrease program run time as the convolution loop
'would only have to be iterated through once for each time step.

Dim PBCA As Double, _
    PBCB As Double, _
    PBC As Double, _
    PBCOld As Double

PBC = 0
If n = 2 Then
    PastBackCurv = PBC
Else
    For j = 1 To n - 2
        PBCA = 0.5 * (C(j + 1) + C(j))
        PBCB = t(j + 1) - t(j)
        If j = 1 Then
            PBC = PBCA * PBCB
            PBCOld = PBC
        Else
            PBC = PBCOld + PBCA * PBCB
            PBCOld = PBC
        End If
    Next j
    PastBackCurv = PBC
End If

End Function


Function Equal(n As Integer, _
               EQX As Double, _
               EQY As Double, _
               EQZ As Double, _
               EQW As Double)

'This function contains the Ward and Tordai equality [just the Ward and
'Tordai equation rearranged so that it equals zero].  Estimates of
'surface concentration will be filtered through this function to see
'how close the equality is to zero.

Dim EQA As Double, _
    EQB As Double, _
    EQC As Double, _
    EQD As Double, _
    EQF1 As Double, _
    EQF2A As Double

EQF1 = 1
EQF2 = 1
If boolkmic Then 'Calculate micelle correction factors
    EQF1 = kmicF1(t(n))
    EQF2 = kmicF2(t(n) - t(n - 1))
End If

EQA = Sqr(4 * D / Pi)
EQB = EQF1 * C(0) * Sqr(t(n))
EQC = -0.5 * (EQY + EQF2 * C(n - 1)) * Sqr(t(n) - t(n - 1))
EQD = 0

If boolB Then 'Calculate curvature effect
    EQD = C(0) * t(n) - 0.5 * (EQY + C(n - 1)) * (t(n) - t(n - 1)) - EQW
    EQD = (D / B) * EQD
End If

Equal = EQX - EQA * (EQB + EQC + EQZ) - EQD

End Function


Function kmicF1(tmic)

'This function calculates the first correction factor to the Ward and
'Tordai equation when considering a solution in which micelles break up.
'See the function "kmicF2" also

Dim kmicA As Double, _
    kmicB As Double

kmicA = (0.5 + kmic * tmic) * ErfCalc(Sqr(kmic * tmic))
kmicB = Sqr(kmic * tmic / Pi) * Exp(-kmic * tmic)   'Not sure about the factor of 2 here...
kmicF1 = Sqr(Pi / (4 * kmic * tmic)) * (kmicA + kmicB)

End Function


Function kmicF2(tmic)

'This function calculates the second correction factor to the Ward and
'Tordai equation when considering a solution in which micelles break up.
'See the function "kmicF1" also

Dim kmicA As Double, _
    kmicB As Double

kmicA = Exp(-kmic * tmic) / Sqr(Pi)
kmicB = Sqr(kmic * tmic) * ErfCalc(Sqr(kmic * tmic))
kmicF2 = Sqr(Pi) * (kmicA + kmicB)

End Function


Function ErfCalc(x)

'This is the Error Function adapted using the asymptotic expressions
'listed at mathworld.wolfram.com.

Dim Nerf As Integer, _
    x1 As Double, _
    x2 As Double, _
    z1 As Double, _
    z2 As Double, _
    dx As Double, _
    ErfSum As Double, _
    ErfSumOld As Double, _
    PiErf As Double

PiErf = 3.14159265358979

If x < 0.4 Then
    ErfSum = (2 / Sqr(PiErf)) * x * Exp(-x ^ 2) * (1 + (2 * x ^ 2) / 3 + (2 * x ^ 2) ^ 2 / 15)
ElseIf x > 1.9 Then
    ErfSum = 1 - (Exp(-x ^ 2) / Sqr(PiErf * x ^ 2)) * (1 - 0.5 / (x ^ 2) + 0.75 / (x ^ 4) - (15 / 8) / (x ^ 6))
Else
    Nerf = 100
    dx = (x - 0) / (Nerf)
    ErfSum = 0
    ErfSumOld = ErfSum
    For erfiter = 1 To (Nerf)
        x1 = (erfiter - 1) * dx
        x2 = erfiter * dx
        z1 = Exp(-x1 ^ 2)
        z2 = Exp(-x2 ^ 2)
        ErfSum = ErfSumOld + 0.5 * (z2 + z1) * (x2 - x1)
        ErfSumOld = ErfSum
    Next erfiter
    ErfSum = (2 / Sqr(PiErf)) * ErfSum
End If

ErfCalc = ErfSum
End Function
