export default function BackgroundFX() {
  return (
    <>
      <div className="fixed inset-0 scanlines z-50"></div>
      <div className="watermark-chrono">CHRONOGRAPH</div>
      <div className="fixed inset-0 z-0 opacity-10 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-primary via-transparent to-transparent"></div>
    </>
  )
}
