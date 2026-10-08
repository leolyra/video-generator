import os
import uuid
import asyncio
import subprocess
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Video Generator - FFmpeg & Edge-TTS")

class VideoRequest(BaseModel):
    texto: str
    imagem_url: str
    voz: str = "pt-BR-AntonioNeural"  # Opções: pt-BR-AntonioNeural ou pt-BR-FranciscaNeural
    duracao_segundos: int = 15

@app.post("/gerar-video")
async def gerar_video(req: VideoRequest):
    job_id = str(uuid.uuid4())[:8]
    work_dir = f"/tmp/job_{job_id}"
    os.makedirs(work_dir, exist_ok=True)

    img_path = os.path.join(work_dir, "input.jpg")
    audio_path = os.path.join(work_dir, "audio.mp3")
    output_path = os.path.join(work_dir, "video_15s.mp4")

    try:
        # 1. Download da foto do produto
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(req.imagem_url, headers=headers, timeout=20)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao baixar imagem da URL informada")
        with open(img_path, "wb") as f:
            f.write(resp.content)

        # 2. Locução neural gratuita via Edge-TTS (PT-BR)
        texto_limpo = req.texto.replace('"', '').replace("'", "")
        cmd_tts = f'edge-tts --voice "{req.voz}" --text "{texto_limpo}" --write-media "{audio_path}"'
        proc_tts = await asyncio.create_subprocess_shell(cmd_tts)
        await proc_tts.communicate()

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise HTTPException(status_code=500, detail="Falha ao gerar locução de áudio")

        # 3. Renderização FFmpeg: Imagem 9:16 (1080x1920) com zoom suave + Áudio narrado
        duracao = req.duracao_segundos
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(duracao), "-i", img_path,
            "-i", audio_path,
            "-filter_complex",
            (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                f"zoompan=z='min(zoom+0.0012,1.15)':d={duracao*25}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            output_path
        ]

        proc_ffmpeg = await asyncio.create_subprocess_exec(*cmd_ffmpeg)
        await proc_ffmpeg.communicate()

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Falha ao renderizar vídeo com FFmpeg")

        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename="video_apresentacao_15s.mp4"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
