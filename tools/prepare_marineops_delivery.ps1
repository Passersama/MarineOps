param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
public static class MarineOpsAlpha {
    public static int[] Components(bool[] m,int w,int h) {
        bool[] seen=new bool[m.Length]; var sizes=new List<int>();
        int[] queue=new int[m.Length];
        for(int i=0;i<m.Length;i++) if(m[i]&&!seen[i]) {
            int head=0,tail=1;queue[0]=i;seen[i]=true;
            while(head<tail) {int p=queue[head++],x=p%w,y=p/w;
                for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
                    int xx=x+dx,yy=y+dy;if(xx<0||yy<0||xx>=w||yy>=h)continue;
                    int n=yy*w+xx;if(m[n]&&!seen[n]){seen[n]=true;queue[tail++]=n;}
                }
            } sizes.Add(tail);
        } sizes.Sort((a,b)=>b.CompareTo(a)); return sizes.ToArray();
    }
    public static bool[] Largest(bool[] m,int w,int h) {
        bool[] seen=new bool[m.Length],best=new bool[m.Length];
        int[] queue=new int[m.Length]; int largest=0;
        for(int i=0;i<m.Length;i++)if(m[i]&&!seen[i]) {
            int head=0,tail=1;queue[0]=i;seen[i]=true;
            while(head<tail){int p=queue[head++],x=p%w,y=p/w;
                for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){
                    int xx=x+dx,yy=y+dy;if(xx<0||yy<0||xx>=w||yy>=h)continue;
                    int n=yy*w+xx;if(m[n]&&!seen[n]){seen[n]=true;queue[tail++]=n;}
                }
            }
            if(tail>largest){Array.Clear(best,0,best.Length);for(int j=0;j<tail;j++)best[queue[j]]=true;largest=tail;}
        }return best;
    }
    static bool[] Morph(bool[] m,int w,int h,int r,bool dilate){
        bool[] o=new bool[m.Length];
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            bool v=!dilate;bool done=false;
            for(int dy=-r;dy<=r&&!done;dy++)for(int dx=-r;dx<=r;dx++){
                if(dx*dx+dy*dy>r*r)continue;
                int xx=x+dx,yy=y+dy;bool q=xx>=0&&yy>=0&&xx<w&&yy<h&&m[yy*w+xx];
                if(dilate&&q){v=true;done=true;break;}if(!dilate&&!q){v=false;done=true;break;}
            }o[y*w+x]=v;
        }return o;
    }
    public static byte[] Clean(byte[] rgba,int w,int h,out int before,out int after,out int changed){
        bool[] m=new bool[w*h];for(int i=0;i<m.Length;i++)m[i]=rgba[i*4+3]>=128;
        before=Components(m,w,h).Length;bool[] main=Largest(m,w,h);
        bool[] opened=Morph(Morph(main,w,h,2,false),w,h,2,true);
        opened=Largest(opened,w,h);
        int[] k={1,4,6,4,1}; byte[] output=(byte[])rgba.Clone();changed=0;
        for(int y=0;y<h;y++)for(int x=0;x<w;x++){
            int sum=0;for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++){
                int xx=x+dx,yy=y+dy;if(xx>=0&&yy>=0&&xx<w&&yy<h&&opened[yy*w+xx])sum+=k[dx+2]*k[dy+2];
            }
            int a=(int)Math.Round(sum*255.0/256);if(a<8)a=0;if(a>247)a=255;
            int index=(y*w+x)*4;if(a!=rgba[index+3])changed++;
            output[index+3]=(byte)a;
            if(a==0){output[index]=output[index+1]=output[index+2]=0;continue;}
            if(rgba[index+3]<240){
                int nearest=-1,best=999;
                for(int dy=-5;dy<=5;dy++)for(int dx=-5;dx<=5;dx++){
                    int xx=x+dx,yy=y+dy;if(xx<0||yy<0||xx>=w||yy>=h)continue;
                    int n=yy*w+xx,d=dx*dx+dy*dy;
                    if(opened[n]&&rgba[n*4+3]>=240&&d<best){nearest=n;best=d;}
                }
                if(nearest>=0)for(int c=0;c<3;c++)output[index+c]=rgba[nearest*4+c];
            }
        }
        bool[] final=new bool[w*h];for(int i=0;i<final.Length;i++)final[i]=output[i*4+3]>=128;
        after=Components(final,w,h).Length;return output;
    }
}
'@
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$pngDir=Join-Path $Destination 'png'
$iconDir=Join-Path $Destination 'icons'
New-Item -ItemType Directory -Force -Path $pngDir,$iconDir | Out-Null
$inputImage=[System.Drawing.Bitmap]::new($Source)
$rect=[System.Drawing.Rectangle]::new(0,0,$inputImage.Width,$inputImage.Height)
$data=$inputImage.LockBits($rect,[System.Drawing.Imaging.ImageLockMode]::ReadOnly,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
if($data.Stride -ne $inputImage.Width*4){throw 'Unexpected source stride'}
$bytes=[byte[]]::new($data.Stride*$data.Height)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0,$bytes,0,$bytes.Length)
$inputImage.UnlockBits($data)
[int]$before=0;[int]$after=0;[int]$changed=0
$clean=[MarineOpsAlpha]::Clean($bytes,$inputImage.Width,$inputImage.Height,[ref]$before,[ref]$after,[ref]$changed)
if($after -ne 1){throw "Unexpected component count: $after"}
$cleanImage=[System.Drawing.Bitmap]::new($inputImage.Width,$inputImage.Height,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$writeData=$cleanImage.LockBits($rect,[System.Drawing.Imaging.ImageLockMode]::WriteOnly,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
[System.Runtime.InteropServices.Marshal]::Copy($clean,0,$writeData.Scan0,$clean.Length)
$cleanImage.UnlockBits($writeData)
$minX=$inputImage.Width;$minY=$inputImage.Height;$maxX=0;$maxY=0
for($y=0;$y -lt $inputImage.Height;$y++){for($x=0;$x -lt $inputImage.Width;$x++){if($clean[($y*$inputImage.Width+$x)*4+3] -gt 0){$minX=[Math]::Min($minX,$x);$minY=[Math]::Min($minY,$y);$maxX=[Math]::Max($maxX,$x);$maxY=[Math]::Max($maxY,$y)}}}
$bounds=[System.Drawing.Rectangle]::new($minX,$minY,$maxX-$minX+1,$maxY-$minY+1)
$master=[System.Drawing.Bitmap]::new($bounds.Width+96,$bounds.Height+96,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics=[System.Drawing.Graphics]::FromImage($master)
$graphics.CompositingMode=[System.Drawing.Drawing2D.CompositingMode]::SourceCopy
$graphics.DrawImage($cleanImage,[System.Drawing.Rectangle]::new(48,48,$bounds.Width,$bounds.Height),$bounds,[System.Drawing.GraphicsUnit]::Pixel)
$graphics.Dispose()
$master.Save((Join-Path $Destination 'marineops-symbol-master.png'),[System.Drawing.Imaging.ImageFormat]::Png)
function Export-Symbol([int]$Width,[int]$Height,[string]$Path,[bool]$Square=$false){
    $bitmap=[System.Drawing.Bitmap]::new($Width,$Height,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g=[System.Drawing.Graphics]::FromImage($bitmap)
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode=[System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.CompositingQuality=[System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $fit=if($Square){0.90}else{1.0}
    $scale=[Math]::Min($Width/$master.Width,$Height/$master.Height)*$fit
    $dw=[Math]::Max(1,[int][Math]::Round($master.Width*$scale));$dh=[Math]::Max(1,[int][Math]::Round($master.Height*$scale))
    $g.DrawImage($master,[System.Drawing.Rectangle]::new([int](($Width-$dw)/2),[int](($Height-$dh)/2),$dw,$dh))
    $g.Dispose();$bitmap.Save($Path,[System.Drawing.Imaging.ImageFormat]::Png);$bitmap.Dispose()
}
foreach($width in @(1536,1024,512,256)){
    $height=[int][Math]::Round($width*$master.Height/$master.Width)
    Export-Symbol $width $height (Join-Path $pngDir "marineops-symbol-$width.png")
}
$iconSizes=@(16,20,24,32,48,64,128,256,512,1024)
foreach($size in $iconSizes){Export-Symbol $size $size (Join-Path $iconDir "marineops-$size.png") $true}
$icoSizes=@(16,20,24,32,48,64,128,256)
$stream=[System.IO.File]::Create((Join-Path $Destination 'marineops.ico'))
$writer=[System.IO.BinaryWriter]::new($stream)
$writer.Write([uint16]0);$writer.Write([uint16]1);$writer.Write([uint16]$icoSizes.Count)
$offset=6+16*$icoSizes.Count
$frames=@()
foreach($size in $icoSizes){
    $frame=[System.IO.File]::ReadAllBytes((Join-Path $iconDir "marineops-$size.png"));$frames+=,$frame
    $encoded=if($size -eq 256){0}else{$size}
    $writer.Write([byte]$encoded);$writer.Write([byte]$encoded);$writer.Write([byte]0);$writer.Write([byte]0)
    $writer.Write([uint16]1);$writer.Write([uint16]32);$writer.Write([uint32]$frame.Length);$writer.Write([uint32]$offset)
    $offset+=$frame.Length
}
foreach($frame in $frames){$writer.Write([byte[]]$frame)}
$writer.Dispose();$stream.Dispose()
$preview=[System.Drawing.Bitmap]::new(1440,1000)
$g=[System.Drawing.Graphics]::FromImage($preview)
$g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode=[System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$font=[System.Drawing.Font]::new('Segoe UI',16)
$smallFont=[System.Drawing.Font]::new('Segoe UI',10)
$backgrounds=@('#000000','#191E23','#20262D','#FFFFFF')
for($i=0;$i -lt 4;$i++){
    $px=($i%2)*720;$py=[int][Math]::Floor($i/2)*500
    $brush=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($backgrounds[$i]))
    $ink=[System.Drawing.SolidBrush]::new($(if($i -eq 3){[System.Drawing.Color]::FromArgb(36,38,43)}else{[System.Drawing.Color]::FromArgb(230,232,237)}))
    $g.FillRectangle($brush,$px,$py,720,500)
    $g.DrawString("MarineOps | $($backgrounds[$i])",$font,$ink,$px+30,$py+20)
    $showHeight=[int][Math]::Round(630*$master.Height/$master.Width)
    $g.DrawImage($master,[System.Drawing.Rectangle]::new($px+45,$py+80,630,$showHeight))
    $cursor=$px+30
    foreach($size in @(16,24,32,48,64,128)){
        $icon=[System.Drawing.Bitmap]::new((Join-Path $iconDir "marineops-$size.png"))
        $g.DrawImageUnscaled($icon,$cursor,$py+355+128-$size)
        $g.DrawString("$size",$smallFont,$ink,$cursor,$py+330)
        $cursor+=$size+24;$icon.Dispose()
    }
    $brush.Dispose();$ink.Dispose()
}
$g.Dispose();$font.Dispose();$smallFont.Dispose()
$preview.Save((Join-Path $Destination 'verification-preview.png'),[System.Drawing.Imaging.ImageFormat]::Png)
$preview.Dispose()
$report=[ordered]@{source=$Source;source_width=$inputImage.Width;source_height=$inputImage.Height;components_before=$before;components_after=$after;alpha_pixels_changed=$changed;master_width=$master.Width;master_height=$master.Height;bounds=@($bounds.X,$bounds.Y,$bounds.Width,$bounds.Height);icon_sizes=$icoSizes;backgrounds=$backgrounds;method='Largest connected alpha component, radius-2 contour opening, antialias reconstruction, transparent RGB sanitation; generated ribbon RGB retained.'}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Destination 'verification.json') -Encoding utf8
$master.Dispose();$cleanImage.Dispose();$inputImage.Dispose()
$report | ConvertTo-Json -Depth 4
