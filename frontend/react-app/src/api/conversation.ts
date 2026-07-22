export async function clearConversation(conversationId: string): Promise<void> {
  const response = await fetch(
    `/api/conversations/${encodeURIComponent(conversationId)}`,
    { method: 'DELETE' },
  )
  if (response.status !== 204) throw new Error(`HTTP ${response.status}`)
}
