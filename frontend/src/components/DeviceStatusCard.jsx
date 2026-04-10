import styles from '../styles/DeviceStatusCard.module.css'

const STATUS = {
  checking: { label: '확인 중...', color: '#aaa' },
  granted: { label: '허용됨', color: '#50eba0' },
  denied: { label: '거부됨', color: '#f07070' },
}

export default function DeviceStatusCard({ type, status, videoRef }) {
  const isCamera = type === 'camera'
  const info = STATUS[status] || STATUS.checking

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.iconWrap}>
          {isCamera ? (
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="2" y="7" width="21" height="18" rx="3" fill="currentColor" opacity="0.15"/>
              <rect x="2" y="7" width="21" height="18" rx="3" stroke="currentColor" strokeWidth="2"/>
              <circle cx="12.5" cy="16" r="4.5" stroke="currentColor" strokeWidth="2"/>
              <circle cx="12.5" cy="16" r="2" fill="currentColor"/>
              <polygon points="23,12 30,9 30,23 23,20" fill="currentColor" opacity="0.8"/>
            </svg>
          ) : (
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="11" y="2" width="10" height="18" rx="5" fill="currentColor" opacity="0.15"/>
              <rect x="11" y="2" width="10" height="18" rx="5" stroke="currentColor" strokeWidth="2"/>
              <path d="M6 16c0 5.523 4.477 10 10 10s10-4.477 10-10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              <line x1="16" y1="26" x2="16" y2="30" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              <line x1="11" y1="30" x2="21" y2="30" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          )}
        </div>
        <div className={styles.info}>
          <span className={styles.deviceName}>{isCamera ? '웹캠' : '마이크'}</span>
          <span className={styles.statusBadge} style={{ color: info.color }}>
            <span className={styles.dot} style={{ background: info.color }} />
            {info.label}
          </span>
        </div>
      </div>

      {/* 웹캠 미리보기 */}
      {isCamera && (
        <div className={styles.preview}>
          {status === 'granted' ? (
            <video ref={videoRef} autoPlay muted playsInline className={styles.video} />
          ) : (
            <div className={styles.previewPlaceholder}>
              {status === 'denied'
                ? '웹캠 권한이 거부되었습니다.\n브라우저 설정에서 허용해주세요.'
                : '웹캠 권한을 요청 중입니다...'}
            </div>
          )}
        </div>
      )}

      {/* 마이크 안내 */}
      {!isCamera && status === 'denied' && (
        <p className={styles.deniedMsg}>
          마이크 권한이 거부되었습니다. 브라우저 설정에서 허용해주세요.
        </p>
      )}
    </div>
  )
}
