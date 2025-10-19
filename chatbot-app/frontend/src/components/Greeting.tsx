"use client"

export function Greeting() {
  return (
    <div className="w-full flex flex-col justify-center items-center min-h-[60vh] relative overflow-hidden">
      {/* 🎬 Background GIF */}
      <img
        src="/bosesberde-bg.gif"
        alt="Boses Berde background"
        className="absolute inset-0 w-full h-full object-cover opacity-40"
      />

      {/* 🟩 Overlay text */}
      <div className="relative z-10 text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-balance animate-fade-in">
          Welcome to{" "}
          <span className="bg-gradient-to-r from-green-600 via-emerald-500 to-lime-500 bg-clip-text text-transparent dark:from-green-400 dark:via-lime-300 dark:to-emerald-400">
            Boses Berde
          </span>
        </h1>

        <p className="mt-4 text-lg text-gray-800 dark:text-gray-100 animate-fade-in delay-300">
          Empowering youth into green and sustainable careers 🌱
        </p>
      </div>
    </div>
  )
}
