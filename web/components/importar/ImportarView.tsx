"use client";
import Link from 'next/link'
import { FileUploader } from '@/components/importar/FileUploader'

export function ImportarView() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">📥 Importar treinos</h1>
      <p className="text-sm text-slate-500">
        Conecte um dispositivo em{' '}
        <Link href="/conexoes" className="font-medium text-blue-600 underline">Conexões</Link>{' '}
        para importar treinos automaticamente.
      </p>
      <FileUploader />
    </div>
  )
}
