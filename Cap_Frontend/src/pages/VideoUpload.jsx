import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import AppLogo from '../components/AppLogo'
import styles from '../styles/VideoUpload.module.css'
import { uploadVideo } from '../lib/api'

const ACCEPTED = '.mp4,.avi,.mov,.mkv'
const ACCEPTED_TYPES = ['video/mp4', 'video/x-msvideo', 'video/quicktime', 'video/x-matroska']

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function VideoUpload() {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)

  function handleFile(f) {
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    const validExts = ['mp4', 'avi', 'mov', 'mkv']
    if (!validExts.includes(ext) && !ACCEPTED_TYPES.includes(f.type)) {
      setError('지원하지 않는 형식입니다. mp4, avi, mov, mkv 파일을 선택해주세요.')
      setFile(null)
      return
    }
    setError('')
    setFile(f)
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  function onInputChange(e) {
    handleFile(e.target.files[0])
  }

  async function onStart() {
    if (!file || uploading) return
    setUploading(true)
    setError('')
    try {
      const { job_id } = await uploadVideo(file)
      navigate('/loading', { state: { fileName: file.name, jobId: job_id } })
    } catch (err) {
      setError('업로드 중 오류가 발생했습니다. 백엔드 서버가 실행 중인지 확인해주세요.')
      setUploading(false)
    }
  }

  return (
    <div className={styles.container}>
      <AppLogo />
      <div className={styles.gradientMint} />
      <div className={styles.gradientBlue} />

      <div className={styles.content}>
        <h2 className={styles.title}>영상 파일 업로드</h2>
        <p className={styles.desc}>분석할 모의면접 영상을 선택하거나 드래그하세요.</p>

        <div
          className={`${styles.dropzone} ${dragging ? styles.dragging : ''} ${file ? styles.hasFile : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && inputRef.current?.click()}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className={styles.hiddenInput}
            onChange={onInputChange}
            disabled={uploading}
          />

          {file ? (
            <div className={styles.fileInfo}>
              <div className={styles.fileIcon}>
                <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="8" y="4" width="26" height="40" rx="4" fill="var(--color-accent-light-mint)" stroke="var(--color-green)" strokeWidth="2"/>
                  <path d="M28 4v12h12" stroke="var(--color-green)" strokeWidth="2"/>
                  <polygon points="19,18 33,26 19,34" fill="var(--color-green)" opacity="0.7"/>
                </svg>
              </div>
              <span className={styles.fileName}>{file.name}</span>
              <span className={styles.fileSize}>{formatBytes(file.size)}</span>
              {!uploading && <span className={styles.changeHint}>다른 파일 선택</span>}
            </div>
          ) : (
            <div className={styles.placeholder}>
              <div className={styles.uploadIcon}>
                <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="24" cy="24" r="22" fill="var(--color-accent-light-blue)" opacity="0.7"/>
                  <path d="M24 32V20M24 20l-5 5M24 20l5 5" stroke="var(--color-blue)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M14 36h20" stroke="var(--color-blue)" strokeWidth="2.5" strokeLinecap="round" opacity="0.5"/>
                </svg>
              </div>
              <span className={styles.placeholderText}>영상 파일을 선택하거나 드래그하세요</span>
              <span className={styles.formatHint}>mp4, avi, mov, mkv 지원</span>
            </div>
          )}
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button
            className={styles.startBtn}
            disabled={!file || uploading}
            onClick={onStart}
          >
            {uploading ? '업로드 중...' : '분석 시작'}
          </button>
          <button
            className={styles.backBtn}
            onClick={() => navigate('/')}
            disabled={uploading}
          >
            뒤로가기
          </button>
        </div>
      </div>
    </div>
  )
}
