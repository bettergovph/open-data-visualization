/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  safelist: [
    'bg-[#17a2b8]', 'bg-[#28a745]', 'bg-[#6c757d]', 'bg-[#dc3545]', 'bg-[#ffc107]',
    'bg-black', 'bg-blue-100', 'bg-blue-50', 'bg-blue-600', 'bg-gradient-to-br',
    'bg-gradient-to-r', 'bg-gray-100', 'bg-gray-50', 'bg-gray-600', 'bg-green-100',
    'bg-green-50', 'bg-green-600', 'bg-red-100', 'bg-red-50', 'bg-white',
    'bg-yellow-100', 'bg-yellow-50', 'block', 'border-2', 'border-4', 'border-b',
    'border-b-2', 'border-black', 'border-blue-200', 'border-blue-500', 'border-blue-600',
    'border-gray-200', 'border-gray-300', 'border-green-200', 'border-green-400',
    'border-green-500', 'border-l', 'border-l-4', 'border-r', 'border-red-400',
    'border-red-500', 'border-t', 'border-t-blue-900', 'border-yellow-400',
    'flex', 'flex-col', 'flex-shrink-0', 'focus:outline-none', 'gap-2', 'gap-3',
    'gap-4', 'gap-5', 'gap-6', 'gap-8', 'grid', 'grid-cols-1', 'grid-cols-2',
    'h-10', 'h-12', 'h-3', 'h-6', 'h-8', 'h-96', 'hidden', 'hover:bg-blue-700',
    'hover:bg-gray-200', 'hover:bg-gray-700', 'hover:bg-gray-800', 'hover:bg-green-700',
    'hover:shadow-lg', 'hover:shadow-xl', 'hover:text-gray-600', 'items-center',
    'items-start', 'justify-between', 'justify-center', 'm-0', 'max-w-2xl',
    'max-w-7xl', 'max-w-full', 'min-w-full', 'p-10', 'p-3', 'p-4', 'p-5', 'p-6', 'p-8',
    'rounded-full', 'rounded-lg', 'rounded-md', 'rounded-t-lg', 'rounded-xl',
    'shadow-lg', 'shadow-md', 'shadow-sm', 'space-x-6', 'space-y-1', 'space-y-2',
    'space-y-3', 'space-y-4', 'text-2xl', 'text-3xl', 'text-base', 'text-black',
    'text-blue-600', 'text-blue-700', 'text-blue-800', 'text-blue-900', 'text-center',
    'text-gray-500', 'text-gray-600', 'text-gray-700', 'text-gray-800', 'text-green-500',
    'text-green-600', 'text-green-700', 'text-green-800', 'text-left', 'text-lg',
    'text-orange-500', 'text-orange-600', 'text-purple-600', 'text-red-600',
    'text-red-700', 'text-red-800', 'text-sm', 'text-white', 'text-xl', 'text-xs',
    'text-yellow-700', 'text-yellow-800', 'w-10', 'w-12', 'w-3', 'w-6', 'w-full',
    // Additional utility patterns
    'md:flex', 'md:hidden', 'py-2', 'py-4', 'py-8', 'px-4', 'px-6', 'mx-auto', 'mr-3',
    'mt-4', 'mb-2', 'mb-4', 'font-bold', 'font-medium', 'transition', 'transition-all',
    'duration-300', 'inline-block', 'inline-flex', 'opacity-90', 'uppercase', 'no-underline'
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}

